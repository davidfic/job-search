"""
apply_util - compose and send a job application from the app.

Stdlib only (smtplib + email). Two ways out, both reviewed by the user first:
  - send_email(): real send through the user's OWN email account, resume attached
  - a mailto: draft is built in jobhunt_web (no attachment possible there)

build_cover() fills the cover-note template with the listing + applicant details.
Nothing here is bulk: callers send one application at a time after explicit confirm.
"""

import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote


def build_cover(template, job, applicant):
    """Fill {name}/{job_title}/{company}/{my_email}/{my_phone} in the template.
    Missing fields become empty strings rather than raising."""
    fields = {
        "name": applicant.get("name", ""),
        "my_email": applicant.get("email", ""),
        "my_phone": applicant.get("phone", ""),
        "job_title": job.get("title", "") or "the role",
        "company": job.get("company", "") or "your team",
    }

    class _Safe(dict):
        def __missing__(self, k):
            return ""

    return (template or "").format_map(_Safe(fields))


def default_subject(job, applicant):
    title = job.get("title") or "your opening"
    name = applicant.get("name") or ""
    tail = f" - {name}" if name else ""
    return f"Application: {title}{tail}"


def mailto_url(to, subject, body):
    return (f"mailto:{quote(to)}"
            f"?subject={quote(subject)}&body={quote(body)}")


def _smtp_ok(smtp):
    return bool(smtp.get("host") and smtp.get("user") and smtp.get("password"))


def test_smtp(smtp):
    """Connect + log in only (sends no mail). Returns (ok, message)."""
    if not _smtp_ok(smtp):
        return False, "SMTP not configured (need host, user, password)."
    try:
        _login(smtp).quit()
        return True, "Connected and signed in successfully."
    except Exception as e:                       # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _login(smtp):
    host = smtp["host"]
    port = int(smtp.get("port") or 587)
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=20,
                                  context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
    server.login(smtp["user"], smtp["password"])
    return server


def send_email(smtp, from_addr, to_addr, subject, body, attachment_path=None):
    """Send one email through the user's own SMTP account, optionally attaching
    the resume. Raises on failure; returns None on success."""
    if not _smtp_ok(smtp):
        raise RuntimeError("SMTP is not configured -- add it in Settings first.")
    if not to_addr:
        raise ValueError("no recipient")

    msg = EmailMessage()
    from_name = smtp.get("from_name") or ""
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body or "")

    if attachment_path:
        if not os.path.isfile(attachment_path):
            raise FileNotFoundError("resume file is missing")
        ctype, _ = mimetypes.guess_type(attachment_path)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        with open(attachment_path, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                               filename=os.path.basename(attachment_path))

    server = _login(smtp)
    try:
        server.send_message(msg)
    finally:
        server.quit()
