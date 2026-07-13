"""
update_util - in-app self-updater.

Checks GitHub for new commits on main, downloads the repo zipball, and swaps
the app's own files in place. Personal data is protected by design: only paths
on an explicit whitelist (update_manifest.json) are ever written, and the db /
config / secrets / resumes can't be added to it. Before swapping, current files
are copied to .backup/ and a pending marker is written; _boot.py uses those to
roll back automatically if the new version fails to start.

Disabled entirely inside a git checkout -- developers update with git pull,
and the updater must never overwrite a working tree.
"""

import datetime as dt
import io
import json
import os
import shutil
import threading
import time
import zipfile

import requests

import jobhunt

REPO = "davidfic/job-search"
BRANCH = "main"
API_LATEST = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
API_COMPARE = f"https://api.github.com/repos/{REPO}/compare/{{base}}...{{head}}"
ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
UA = {"User-Agent": "jobhunt-updater"}

HERE = jobhunt.HERE
VERSION_PATH = os.path.join(HERE, "version.json")
MANIFEST_PATH = os.path.join(HERE, "update_manifest.json")
BACKUP_DIR = os.path.join(HERE, ".backup")
PENDING_PATH = os.path.join(HERE, ".update_pending.json")

CHECK_INTERVAL = 12 * 3600          # in-memory cache; a fresh check per day-ish
RESTART_EXIT_CODE = 42              # _boot.py relaunches the server on this code

# Paths that may never be written by an update, no matter what the downloaded
# manifest says. Everything the user owns lives here.
PROTECTED = {"jobhunt.db", "jobhunt_config.json", "jobhunt_secrets.json",
             "exclude_keywords.txt", "version.json"}
PROTECTED_PREFIXES = ("resumes/", ".venv/", ".backup/", ".git/")

# Fallback whitelist if no update_manifest.json is available at all.
FALLBACK_PATHS = ["jobhunt.py", "jobhunt_web.py", "web/"]

_LOCK = threading.Lock()
_cache = {"at": 0.0, "result": None}


def is_git_checkout():
    return os.path.isdir(os.path.join(HERE, ".git"))


def current_version():
    """The installed version stamp, or None (fresh install from a zip)."""
    try:
        with open(VERSION_PATH, encoding="utf-8") as f:
            v = json.load(f)
        return v if v.get("sha") else None
    except (OSError, ValueError):
        return None


def _write_version(sha, date):
    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        json.dump({"sha": sha, "date": date,
                   "installed_at": dt.datetime.now().isoformat(timespec="seconds")},
                  f, indent=2)


def _safe_path(rel):
    """True if rel is a sane repo-relative path an update may write."""
    if not rel or rel.startswith(("/", "\\")) or ".." in rel.split("/"):
        return False
    if rel in PROTECTED or any(rel.startswith(p) for p in PROTECTED_PREFIXES):
        return False
    return True


def _load_manifest_paths(text):
    try:
        paths = json.loads(text).get("paths") or []
    except ValueError:
        return None
    ok = [p for p in paths if isinstance(p, str) and _safe_path(p)]
    return ok or None


def _local_manifest_paths():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return _load_manifest_paths(f.read())
    except OSError:
        return None


def _summaries(base, head):
    """First lines of the commits between the installed and latest version --
    shown to the user as what's-new notes. Best effort; [] on any problem."""
    try:
        r = requests.get(API_COMPARE.format(base=base, head=head),
                         headers=UA, timeout=15)
        r.raise_for_status()
        commits = r.json().get("commits") or []
        return [c["commit"]["message"].split("\n", 1)[0]
                for c in reversed(commits)][:20]
    except Exception:                                        # noqa: BLE001
        return []


def check(force=False):
    """Compare the installed version against the latest commit on main."""
    if is_git_checkout():
        return {"git": True, "available": False, "current": current_version()}
    now = time.time()
    with _LOCK:
        if not force and _cache["result"] and now - _cache["at"] < CHECK_INTERVAL:
            return _cache["result"]
    r = requests.get(API_LATEST, headers=UA, timeout=15)
    r.raise_for_status()
    j = r.json()
    latest = {"sha": j["sha"],
              "date": (j.get("commit", {}).get("committer") or {}).get("date", ""),
              "message": j.get("commit", {}).get("message", "").split("\n", 1)[0]}
    cur = current_version()
    available = not cur or cur["sha"] != latest["sha"]
    notes = _summaries(cur["sha"], latest["sha"]) if (cur and available) else []
    result = {"current": cur, "latest": latest, "available": available,
              "notes": notes, "first_update": available and not cur}
    with _LOCK:
        _cache.update(at=now, result=result)
    return result


def _member_targets(zf):
    """Map whitelisted zip members -> repo-relative target paths.

    The manifest inside the downloaded zip governs (it knows about files added
    in newer versions); the local manifest, then a minimal fallback, back it up.
    Every path still passes _safe_path, so no manifest can touch user data.
    """
    names = zf.namelist()
    if not names:
        raise ValueError("empty zip")
    root = names[0].split("/", 1)[0] + "/"
    for required in ("jobhunt.py", "jobhunt_web.py", "web/index.html"):
        if root + required not in names:
            raise ValueError(f"unexpected zip contents (missing {required})")

    paths = None
    if root + "update_manifest.json" in names:
        paths = _load_manifest_paths(zf.read(root + "update_manifest.json").decode("utf-8"))
    paths = paths or _local_manifest_paths() or FALLBACK_PATHS

    targets = {}
    for name in names:
        if name.endswith("/") or not name.startswith(root):
            continue
        rel = name[len(root):]
        if not _safe_path(rel):
            continue
        for p in paths:
            if rel == p or (p.endswith("/") and rel.startswith(p)):
                targets[name] = rel
                break
    if not targets:
        raise ValueError("nothing to update in the downloaded zip")
    return targets


def _backup(rels):
    if os.path.isdir(BACKUP_DIR):
        shutil.rmtree(BACKUP_DIR)
    for rel in rels:
        src = os.path.join(HERE, rel)
        if os.path.isfile(src):
            dst = os.path.join(BACKUP_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def restore_backup():
    """Copy every backed-up file back into place. Used for rollback."""
    if not os.path.isdir(BACKUP_DIR):
        return 0
    n = 0
    for dirpath, _dirs, files in os.walk(BACKUP_DIR):
        for fn in files:
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, BACKUP_DIR)
            dst = os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    return n


def apply_update():
    """Download the latest zipball and swap the app files in place.

    Returns a summary dict; raises on any failure. If extraction fails halfway,
    the backup is restored immediately so the install is never left mixed.
    The caller decides whether to restart (supervised) or ask the user to.
    """
    if is_git_checkout():
        raise ValueError("This is a git checkout -- update with git pull instead.")
    info = check(force=True)
    if not info["available"]:
        raise ValueError("Already up to date.")
    latest = info["latest"]

    r = requests.get(ZIP_URL, headers=UA, timeout=120)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    targets = _member_targets(zf)

    _backup(sorted(set(targets.values())))
    cur = current_version()
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump({"from": cur and cur["sha"], "to": latest["sha"],
                   "at": dt.datetime.now().isoformat(timespec="seconds")}, f)
    try:
        for name, rel in targets.items():
            dst = os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(dst) or HERE, exist_ok=True)
            with zf.open(name) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
        _write_version(latest["sha"], latest["date"])
    except Exception:
        restore_backup()
        try:
            os.remove(PENDING_PATH)
        except OSError:
            pass
        raise
    with _LOCK:
        _cache.update(at=0.0, result=None)      # next check sees the new version
    return {"ok": True, "to": latest["sha"], "date": latest["date"],
            "files": len(targets)}
