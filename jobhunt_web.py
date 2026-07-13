"""
jobhunt_web - local web app for the jobhunt aggregator.

Launched via `python jobhunt.py serve`. Pure standard library (http.server),
no new dependencies. Serves a small Leaflet frontend from web/ and a JSON API
that reads the same SQLite db / JSON config the CLI uses, so the two stay in
sync. Bind defaults to 127.0.0.1 -- this is a personal tool, not a public server.

API:
  GET  /api/state                       keyword lists, transit lines, home, meta
  GET  /api/jobs?status=&min_score=     scored jobs, each with resolved geo
  POST /api/fetch                        pull all sources, store new matches
  POST /api/mark   {id,status,note}      set a job's status
  POST /api/keywords {list,action,term,weight}   edit positive/negative/exclude
  GET/POST /api/resume                   upload / inspect / delete the resume
  POST /api/contact {id}                 scan one listing for contact info
  GET  /api/apply/compose?id=            prefilled application draft + context
  POST /api/apply/send|draft|open {id..} submit an application (logs + marks applied)
  GET  /api/applications                 the outbox / application log
  GET/POST /api/profile                  applicant identity, cover template, SMTP
  POST /api/smtp/test {smtp}             test the email connection
  GET  /api/update/check?force=1         is a newer version on GitHub?
  POST /api/update/apply                 download + install it, then restart
  GET  /api/update/status                result of the last update (shown once)
"""

import json
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import jobhunt
import geo_data
import resume_util
import contact_util
import apply_util
import update_util

WEB_DIR = os.path.join(jobhunt.HERE, "web")


def _positive_keys():
    """Current good-fit keyword terms, used to hide already-added suggestions."""
    cfg = jobhunt.load_config(merge_excludes=False)
    return list(cfg.get("profile", {}).get("keywords_positive", {}).keys())


# --------------------------------------------------------------------------- #
# Config editing helpers (positive/negative -> JSON config; exclude -> txt file)
# --------------------------------------------------------------------------- #
_LOCK = threading.Lock()  # serialize config/file writes across request threads
_KEY = {"positive": "keywords_positive", "negative": "keywords_negative"}


def _set_keyword(listname, term, weight):
    cfg = jobhunt.load_config(merge_excludes=False)
    d = cfg["profile"].setdefault(_KEY[listname], {})
    d[term.strip().lower()] = int(weight)
    jobhunt.save_config(cfg)


def _remove_keyword(listname, term):
    cfg = jobhunt.load_config(merge_excludes=False)
    cfg["profile"].get(_KEY[listname], {}).pop(term.strip().lower(), None)
    jobhunt.save_config(cfg)


def _exclude_path():
    return jobhunt.exclude_file_path(jobhunt.load_config(merge_excludes=False))


def _add_exclude(term):
    term = term.strip()
    path = _exclude_path()
    if not term or not path:
        return
    if term.lower() in jobhunt.read_terms_file(path):
        return
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if text and not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + term.lower() + "\n")


def _remove_exclude(term):
    path = _exclude_path()
    if not path or not os.path.exists(path):
        return
    t = term.strip().lower()
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    kept = [ln for ln in lines if ln.split("#", 1)[0].strip().lower() != t]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)


# --------------------------------------------------------------------------- #
# API payload builders
# --------------------------------------------------------------------------- #
def build_state():
    cfg = jobhunt.load_config(merge_excludes=False)
    prof = cfg.get("profile", {})
    az = cfg.get("sources", {}).get("adzuna", {})
    return {
        "positive": prof.get("keywords_positive", {}),
        "negative": prof.get("keywords_negative", {}),
        "exclude": jobhunt.read_terms_file(_exclude_path()),
        "min_display_score": prof.get("min_display_score", 0),
        "statuses": jobhunt.STATUSES,
        "home": geo_data.HOME,
        "transit": geo_data.TRANSIT,
        "adzuna_ready": bool(az.get("enabled") and az.get("app_id") and az.get("app_key")),
        "app_version": update_util.current_version(),
    }


# Triage views -> the status they filter to. 'all' means no status filter.
_VIEW_STATUS = {"new": "new", "interested": "interested",
                "applied": "applied", "rejected": "rejected"}


def _excluded(row, terms):
    """True if the stored job matches any current exclude term -- the same
    title+company+location+summary, word-boundary check used at fetch time.
    Applied at display so newly-added excludes hide existing jobs without a refetch."""
    if not terms:
        return False
    hay = " ".join(str(row[k] or "") for k in
                   ("title", "company", "location", "summary")).lower()
    return any(jobhunt.has_term(t, hay) for t in terms)


def build_jobs(view=None, min_score=None):
    cfg = jobhunt.load_config()
    prof = cfg["profile"]
    if min_score is None:
        min_score = prof.get("min_display_score", 0)
    excludes = [t.lower() for t in prof.get("exclude", [])]

    conn = jobhunt.db()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE score >= ? ORDER BY score DESC, first_seen DESC",
        (min_score,)).fetchall()
    conn.close()

    # Live exclude filter: drop stored jobs matching the current exclude list.
    kept = [r for r in rows if not _excluded(r, excludes)]

    # Counts reflect the same filtering so tab badges match what's shown.
    counts = {}
    for r in kept:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    # The most recent fetch stamps every new row with the same first_seen, so the
    # newest stamp identifies the batch pulled by the last "Fetch new jobs" run.
    latest = max((r["first_seen"] for r in kept if r["first_seen"]), default=None)
    latest_rows = [r for r in kept if latest and r["first_seen"] == latest]
    counts["latest"] = len(latest_rows)

    if view == "latest":
        shown = latest_rows
    else:
        status = _VIEW_STATUS.get(view)
        shown = [r for r in kept if not status or r["status"] == status]

    jobs = []
    for r in shown:
        geo = geo_data.resolve(r["location"], r["title"])
        jobs.append({
            "id": r["id"], "source": r["source"], "title": r["title"] or "",
            "company": r["company"] or "", "location": r["location"] or "",
            "url": r["url"] or "", "summary": (r["summary"] or "")[:400],
            "posted": r["posted"] or "", "first_seen": r["first_seen"] or "",
            "score": r["score"], "status": r["status"], "note": r["note"] or "",
            "lat": geo and geo["lat"], "lng": geo and geo["lng"],
            "geo": geo["matched"] if geo else None,
            "remote": bool(geo and geo["remote"]),
            "contact_kind": r["contact_kind"],
            "pay": r["pay"] or "",
            "applied_at": r["applied_at"] or "",
        })
    return {"jobs": jobs, "counts": counts}


def do_fetch():
    cfg = jobhunt.load_config()
    conn = jobhunt.db()
    summary = jobhunt.fetch_jobs(conn, cfg)
    conn.close()
    return summary


def do_mark(jid, status, note):
    if status not in jobhunt.STATUSES:
        raise ValueError(f"bad status {status!r}")
    conn = jobhunt.db()
    if not conn.execute("SELECT 1 FROM jobs WHERE id=?", (jid,)).fetchone():
        conn.close()
        raise KeyError(jid)
    applied = (jobhunt.dt.datetime.now().isoformat(timespec="seconds")
               if status == "applied" else None)
    if note is not None:
        conn.execute(
            "UPDATE jobs SET status=?, note=?, applied_at=COALESCE(?, applied_at) WHERE id=?",
            (status, note, applied, jid))
    else:
        conn.execute(
            "UPDATE jobs SET status=?, applied_at=COALESCE(?, applied_at) WHERE id=?",
            (status, applied, jid))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Contact extraction + applying (Phases 1-3)
# --------------------------------------------------------------------------- #
def _get_job(jid):
    conn = jobhunt.db()
    r = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    conn.close()
    if not r:
        raise KeyError(jid)
    return r


def _applicant_and_template(kind="cover_template"):
    cfg = jobhunt.load_config(merge_excludes=False)
    appl = cfg.get("applicant", {}) or {}
    tmpl = (cfg.get("outreach", {}) or {}).get(kind, "")
    if not tmpl:
        tmpl = jobhunt.DEFAULT_CONFIG["outreach"][kind]
    return appl, tmpl


def _smtp():
    return jobhunt.load_secrets().get("smtp", {}) or {}


def _log_application(jid, method, to, subject, body, attachment, status, error):
    conn = jobhunt.db()
    conn.execute(
        """INSERT INTO applications
           (job_id, method, to_addr, subject, body, attachment, status, error, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (jid, method, to, subject, body, attachment, status, error,
         jobhunt.dt.datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def do_contact(jid):
    """Fetch one listing page, extract contact info, cache it on the job row."""
    r = _get_job(jid)
    info = contact_util.scan(r["url"], r["source"])
    conn = jobhunt.db()
    conn.execute(
        """UPDATE jobs SET contact_email=?, contact_phone=?, contact_apply_url=?,
           contact_kind=?, contact_fetched_at=? WHERE id=?""",
        (info["emails"][0] if info["emails"] else None,
         info["phones"][0] if info["phones"] else None,
         info["apply_url"], info["kind"],
         jobhunt.dt.datetime.now().isoformat(timespec="seconds"), jid))
    conn.commit()
    conn.close()
    return info


def _last_applied_to(jid):
    """The address the user last sent/drafted an application to for this job."""
    conn = jobhunt.db()
    row = conn.execute(
        """SELECT to_addr FROM applications
           WHERE job_id=? AND to_addr IS NOT NULL AND to_addr != ''
           ORDER BY id DESC LIMIT 1""", (jid,)).fetchone()
    conn.close()
    return row["to_addr"] if row else ""


def build_compose(jid, mode=None):
    """Everything the composer modal needs: job, cached contact, resume, applicant,
    and a prefilled subject + body. mode='followup' composes a check-in on an
    application instead of a fresh cover note."""
    followup = mode == "followup"
    r = _get_job(jid)
    appl, tmpl = _applicant_and_template(
        "followup_template" if followup else "cover_template")
    job = {"id": r["id"], "title": r["title"] or "", "company": r["company"] or "",
           "url": r["url"] or "", "source": r["source"] or "",
           "location": r["location"] or ""}
    if followup and r["applied_at"]:
        try:
            d = jobhunt.dt.datetime.fromisoformat(r["applied_at"])
            job["applied_when"] = f"on {d.strftime('%B')} {d.day}"
        except ValueError:
            pass
    contact = None
    if r["contact_kind"]:
        contact = {"kind": r["contact_kind"], "email": r["contact_email"],
                   "phone": r["contact_phone"], "apply_url": r["contact_apply_url"]}
    rmeta = resume_util.load_meta()
    to = (contact and contact["email"]) or ""
    if followup:
        to = _last_applied_to(jid) or to
    return {
        "job": job,
        "followup": followup,
        "contact": contact,
        "resume": {"filename": rmeta["filename"]} if rmeta else None,
        "applicant": {k: appl.get(k, "") for k in ("name", "email", "phone")},
        "smtp_configured": apply_util._smtp_ok(_smtp()),
        "to": to,
        "subject": (apply_util.followup_subject(job, appl) if followup
                    else apply_util.default_subject(job, appl)),
        "body": apply_util.build_cover(tmpl, job, appl),
    }


def do_apply_send(jid, to, subject, body):
    r = _get_job(jid)
    smtp = _smtp()
    if not apply_util._smtp_ok(smtp):
        raise ValueError("Email sending isn't set up. Add SMTP in Settings, or use the draft option.")
    if not to:
        raise ValueError("No recipient address.")
    resume_path = resume_util.current_file_path()
    if not resume_path:
        raise ValueError("Upload a resume first so it can be attached.")
    appl, _ = _applicant_and_template()
    from_addr = smtp.get("user") or appl.get("email")
    attach = os.path.basename(resume_path)
    try:
        apply_util.send_email(smtp, from_addr, to, subject, body, resume_path)
    except Exception as e:                       # noqa: BLE001
        _log_application(jid, "smtp", to, subject, body, attach, "failed", str(e))
        raise
    _log_application(jid, "smtp", to, subject, body, attach, "sent", None)
    do_mark(jid, "applied", None)
    return {"ok": True, "to": to}


def do_apply_draft(jid, to, subject, body):
    _get_job(jid)
    if not to:
        raise ValueError("No recipient address.")
    _log_application(jid, "mailto", to, subject, body, None, "drafted", None)
    do_mark(jid, "applied", None)
    return {"mailto": apply_util.mailto_url(to, subject, body)}


def do_apply_open(jid):
    r = _get_job(jid)
    target = r["contact_apply_url"] or r["url"]
    _log_application(jid, "open_page", None, None, None, None, "opened", None)
    do_mark(jid, "applied", None)
    return {"url": target}


def build_applications():
    conn = jobhunt.db()
    rows = conn.execute(
        """SELECT a.id, a.job_id, a.method, a.to_addr, a.subject, a.attachment,
                  a.status, a.error, a.created_at, j.title, j.company
           FROM applications a LEFT JOIN jobs j ON j.id = a.job_id
           ORDER BY a.id DESC LIMIT 100""").fetchall()
    conn.close()
    return {"applications": [dict(r) for r in rows]}


def build_profile():
    appl, tmpl = _applicant_and_template()
    smtp = _smtp()
    return {
        "applicant": {k: appl.get(k, "") for k in ("name", "email", "phone")},
        "cover_template": tmpl,
        "smtp": {"host": smtp.get("host", ""), "port": smtp.get("port", 587),
                 "user": smtp.get("user", ""), "from_name": smtp.get("from_name", ""),
                 "configured": apply_util._smtp_ok(smtp)},
        "has_resume": bool(resume_util.load_meta()),
    }


def save_profile(b):
    cfg = jobhunt.load_config(merge_excludes=False)
    appl = cfg.setdefault("applicant", {})
    for k in ("name", "email", "phone"):
        if k in (b.get("applicant") or {}):
            appl[k] = (b["applicant"].get(k) or "").strip()
    if "cover_template" in b:
        cfg.setdefault("outreach", {})["cover_template"] = b["cover_template"]
    jobhunt.save_config(cfg)

    if b.get("smtp") is not None:                # password is write-only
        secrets = jobhunt.load_secrets()
        smtp = secrets.setdefault("smtp", {})
        s = b["smtp"]
        for k in ("host", "user", "from_name"):
            if k in s:
                smtp[k] = (s.get(k) or "").strip()
        if "port" in s:
            smtp["port"] = int(s.get("port") or 587)
        if s.get("password"):                    # only overwrite when provided
            smtp["password"] = s["password"]
        jobhunt.save_secrets(secrets)
    return build_profile()


def do_smtp_test(b):
    smtp = dict(_smtp())
    s = (b or {}).get("smtp") or {}              # allow testing un-saved form values
    for k in ("host", "user", "from_name"):
        if s.get(k):
            smtp[k] = s[k]
    if s.get("port"):
        smtp["port"] = s["port"]
    if s.get("password"):
        smtp["password"] = s["password"]
    ok, msg = apply_util.test_smtp(smtp)
    return {"ok": ok, "message": msg}


# --------------------------------------------------------------------------- #
# In-app updates
# --------------------------------------------------------------------------- #
def _supervised():
    """True when _boot.py launched us -- it restarts the server on exit code 42."""
    return os.environ.get("JOBHUNT_SUPERVISED") == "1"


def do_update_apply():
    summary = update_util.apply_update()
    summary["restarting"] = _supervised()
    if _supervised():
        # Answer this request first, then hand control back to _boot.py, which
        # starts the new version (and rolls back if it won't boot).
        threading.Timer(0.8, lambda: os._exit(update_util.RESTART_EXIT_CODE)).start()
    return summary


def update_status():
    """One-shot result of the last update attempt, written by _boot.py after
    the restart. Read-and-delete so the toast shows exactly once."""
    path = os.path.join(jobhunt.HERE, ".update_result.json")
    result = None
    try:
        with open(path, encoding="utf-8") as f:
            result = json.load(f)
        os.remove(path)
    except (OSError, ValueError):
        pass
    return {"result": result, "current": update_util.current_version()}


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "jobhunt/1.0"

    def log_message(self, fmt, *a):  # quieter console
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n) or b"{}")

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        try:
            if path == "/api/state":
                return self._json(build_state())
            if path == "/api/jobs":
                qs = parse_qs(u.query)
                view = (qs.get("view") or [None])[0] or None
                ms = (qs.get("min_score") or [None])[0]
                return self._json(build_jobs(view, int(ms) if ms not in (None, "") else None))
            if path == "/api/resume":
                return self._json(resume_util.get_state(_positive_keys()))
            if path == "/api/resume/file":
                return self._serve_resume_file()
            if path == "/api/apply/compose":
                qs = parse_qs(u.query)
                jid = (qs.get("id") or [""])[0]
                mode = (qs.get("mode") or [""])[0]
                return self._json(build_compose(jid, mode or None))
            if path == "/api/applications":
                return self._json(build_applications())
            if path == "/api/profile":
                return self._json(build_profile())
            if path == "/api/update/check":
                force = (parse_qs(u.query).get("force") or ["0"])[0] == "1"
                return self._json(update_util.check(force=force))
            if path == "/api/update/status":
                return self._json(update_status())
            return self._serve_static(path)
        except KeyError as e:
            return self._json({"error": f"no job {e}"}, 404)
        except Exception as e:  # noqa: BLE001 -- surface any error as JSON
            return self._json({"error": str(e)}, 500)

    # ---- POST ----
    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        try:
            if path == "/api/resume":           # raw file bytes, not JSON
                name = (parse_qs(u.query).get("name") or ["resume"])[0]
                n = int(self.headers.get("Content-Length") or 0)
                if n > resume_util.MAX_BYTES:
                    return self._json({"error": "file too large"}, 413)
                data = self.rfile.read(n) if n else b""
                with _LOCK:
                    resume_util.save_resume(name, data)
                return self._json(resume_util.get_state(_positive_keys()))
            if path == "/api/resume/delete":
                with _LOCK:
                    resume_util.delete_resume()
                return self._json({"resume": None, "suggestions": []})
            if path == "/api/fetch":
                with _LOCK:
                    return self._json(do_fetch())
            if path == "/api/contact":
                return self._json(do_contact(self._body().get("id")))
            if path == "/api/apply/send":
                b = self._body()
                with _LOCK:
                    return self._json(do_apply_send(b.get("id"), b.get("to"),
                                                    b.get("subject"), b.get("body")))
            if path == "/api/apply/draft":
                b = self._body()
                return self._json(do_apply_draft(b.get("id"), b.get("to"),
                                                 b.get("subject"), b.get("body")))
            if path == "/api/apply/open":
                return self._json(do_apply_open(self._body().get("id")))
            if path == "/api/profile":
                with _LOCK:
                    return self._json(save_profile(self._body()))
            if path == "/api/smtp/test":
                return self._json(do_smtp_test(self._body()))
            if path == "/api/update/apply":
                with _LOCK:
                    return self._json(do_update_apply())
            if path == "/api/mark":
                b = self._body()
                do_mark(b.get("id"), b.get("status"), b.get("note"))
                return self._json({"ok": True})
            if path == "/api/keywords":
                b = self._body()
                lst, action, term = b.get("list"), b.get("action"), (b.get("term") or "")
                with _LOCK:
                    if lst == "exclude":
                        (_add_exclude if action == "add" else _remove_exclude)(term)
                    elif lst in _KEY:
                        if action == "add":
                            _set_keyword(lst, term, b.get("weight",
                                         4 if lst == "positive" else -4))
                        else:
                            _remove_keyword(lst, term)
                    else:
                        raise ValueError(f"bad list {lst!r}")
                return self._json(build_state())
            return self._json({"error": "not found"}, 404)
        except KeyError as e:
            return self._json({"error": f"no job {e}"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 400)

    def _serve_resume_file(self):
        path = resume_util.current_file_path()
        if not path:
            return self._json({"error": "no resume"}, 404)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition",
                         f'attachment; filename="{os.path.basename(path)}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        full = os.path.realpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(os.path.realpath(WEB_DIR)) or not os.path.isfile(full):
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _lan_ip():
    """Best-effort primary LAN address of this machine, or None. Uses a UDP
    socket to a public IP -- no packets are actually sent, it just makes the OS
    pick the interface it would route through."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), Handler)
    # The host itself always reaches the app on localhost; open the browser there
    # even when bound to 0.0.0.0 (a browser can't connect *to* 0.0.0.0 on Windows).
    local_url = f"http://127.0.0.1:{port}/"
    v = update_util.current_version()
    ver = f"  (version {v['sha'][:7]} of {v['date'][:10]})" if v else ""
    print(f"jobhunt web app running at {local_url}{ver}")
    public = host not in ("127.0.0.1", "localhost", "::1")
    if public:
        lan = _lan_ip()
        if lan:
            print(f"Other devices on this network:  http://{lan}:{port}/")
        print("(Open to your local network -- there is no password, so only do "
              "this on a network you trust.)")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(local_url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        httpd.shutdown()
