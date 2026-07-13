"""
_boot - tiny supervisor the start files run instead of jobhunt.py directly.

Standard library only, and deliberately boring: this file is the safety net
for in-app updates, so it must keep working even when an update breaks the
rest of the app.

What it does, in a loop:
  1. Installs dependencies from requirements.txt when it changed (or first run).
  2. Starts the real server:  python jobhunt.py serve <args>
  3. If a just-applied update is pending (.update_pending.json), health-checks
     the new server over HTTP. Healthy -> the update is confirmed. Server dies
     first -> every file is restored from .backup/ and the old version starts.
  4. Exit code 42 from the server means "restart me" (used after updates);
     anything else ends the loop.

Run:  python _boot.py serve [--host ...] [--port ...]
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PENDING = os.path.join(HERE, ".update_pending.json")
RESULT = os.path.join(HERE, ".update_result.json")
BACKUP = os.path.join(HERE, ".backup")
REQS = os.path.join(HERE, "requirements.txt")
DEPS_STAMP = os.path.join(HERE, ".deps_ok")
RESTART_EXIT_CODE = 42
HEALTH_TIMEOUT = 30


def _read_pending():
    try:
        with open(PENDING, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _clear_pending():
    try:
        os.remove(PENDING)
    except OSError:
        pass


def _write_result(status, pending, detail=""):
    try:
        with open(RESULT, "w", encoding="utf-8") as f:
            json.dump({"status": status, "from": (pending or {}).get("from"),
                       "to": (pending or {}).get("to"), "detail": detail}, f)
    except OSError:
        pass


def ensure_deps():
    """pip install -r requirements.txt, but only when it changed since last time."""
    if not os.path.isfile(REQS):
        return
    try:
        if os.path.isfile(DEPS_STAMP) and os.path.getmtime(DEPS_STAMP) >= os.path.getmtime(REQS):
            return
    except OSError:
        pass
    print("  Installing components (this needs an internet connection)...")
    code = subprocess.call([sys.executable, "-m", "pip", "install",
                            "--quiet", "-r", REQS])
    if code == 0:
        with open(DEPS_STAMP, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        print("  Could not install components -- if jobhunt fails to start,"
              " check your internet connection and try again.")


def rollback():
    n = 0
    if os.path.isdir(BACKUP):
        for dirpath, _dirs, files in os.walk(BACKUP):
            for fn in files:
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, BACKUP)
                dst = os.path.join(HERE, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                n += 1
    return n


def wait_healthy(child, port):
    """Poll the server until it answers, the child dies, or we give up."""
    url = f"http://127.0.0.1:{port}/api/state"
    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        if child.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return child.poll() is None          # alive but slow: assume it's fine


def _port_from(args):
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            try:
                return int(args[i + 1])
            except ValueError:
                pass
        if a.startswith("--port="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                pass
    return 8765


def main():
    args = sys.argv[1:] or ["serve"]
    port = _port_from(args)
    env = dict(os.environ, JOBHUNT_SUPERVISED="1")
    server = os.path.join(HERE, "jobhunt.py")

    while True:
        ensure_deps()
        child = subprocess.Popen([sys.executable, server] + args, env=env, cwd=HERE)
        pending = _read_pending()
        if pending:
            if wait_healthy(child, port):
                _clear_pending()
                _write_result("updated", pending)
            # unhealthy: fall through -- the exit code below decides rollback
        code = child.wait()
        if code == RESTART_EXIT_CODE:
            continue
        pending = _read_pending()
        if pending and code != 0:
            print("  The update failed to start -- restoring the previous version...")
            restored = rollback()
            _clear_pending()
            _write_result("rolled_back", pending,
                          f"restored {restored} files after exit code {code}")
            if restored:
                continue
        _clear_pending()
        sys.exit(code)


if __name__ == "__main__":
    main()
