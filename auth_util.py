"""
auth_util - optional username/password gate for the web app.

Off by default: with no credentials set (or auth.enabled false) the app behaves
exactly as before -- no login, nothing to lock anyone out of. Turn it on only
once a username/password is set, from the CLI (`jobhunt.py set-login`) or the
Settings panel.

Credentials live in jobhunt_secrets.json (chmod 600, never sent to the client)
under an "auth" block: the username and a salted PBKDF2-SHA256 hash of the
password -- the password itself is never stored. Sessions are random tokens kept
in memory, handed out as an HttpOnly, SameSite=Lax cookie; they reset on restart
(you just log in again), which for a personal tool is a fine trade for simplicity.
"""

import hashlib
import hmac
import secrets as _secrets
import threading
import time

import jobhunt

COOKIE = "jobhunt_session"
SESSION_DAYS = 30
_ITERATIONS = 240_000

_lock = threading.Lock()
_sessions = {}                      # token -> expiry epoch seconds


# --------------------------------------------------------------------------- #
# password hashing
# --------------------------------------------------------------------------- #
def hash_password(password, salt=None, iterations=_ITERATIONS):
    if salt is None:
        salt = _secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"algo": "pbkdf2_sha256", "salt": salt.hex(),
            "hash": dk.hex(), "iterations": iterations}


def _verify_password(password, rec):
    try:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(rec["salt"]), int(rec["iterations"]))
    except (KeyError, ValueError):
        return False
    return hmac.compare_digest(dk.hex(), rec.get("hash", ""))


# --------------------------------------------------------------------------- #
# stored credentials (in jobhunt_secrets.json)
# --------------------------------------------------------------------------- #
def _auth():
    return jobhunt.load_secrets().get("auth", {}) or {}


def is_configured():
    """True once a username/password has been set (regardless of enabled)."""
    return bool(_auth().get("hash"))


def is_enabled():
    """True only when auth is both configured and switched on."""
    a = _auth()
    return bool(a.get("enabled") and a.get("hash"))


def get_username():
    return _auth().get("username", "")


def set_login(username, password):
    """Store (or replace) the login. Does not change the enabled flag."""
    username = (username or "").strip()
    if not username:
        raise ValueError("Username can't be empty.")
    if len(password or "") < 6:
        raise ValueError("Use a password of at least 6 characters.")
    s = jobhunt.load_secrets()
    a = s.setdefault("auth", {})
    a["username"] = username
    a.update(hash_password(password))       # algo/salt/hash/iterations
    jobhunt.save_secrets(s)


def set_enabled(on):
    """Turn the login requirement on or off. Refuses to enable with no login set
    so the app can never lock everyone out."""
    on = bool(on)
    if on and not is_configured():
        raise ValueError("Set a username and password before enabling login.")
    s = jobhunt.load_secrets()
    s.setdefault("auth", {})["enabled"] = on
    jobhunt.save_secrets(s)


def verify(username, password):
    a = _auth()
    if not a.get("hash"):
        return False
    # compare the username in constant time too, so it isn't a timing oracle
    user_ok = hmac.compare_digest((username or "").strip(), a.get("username", ""))
    pass_ok = _verify_password(password or "", a)
    return user_ok and pass_ok


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
def create_session(days=SESSION_DAYS):
    tok = _secrets.token_urlsafe(32)
    with _lock:
        _sessions[tok] = time.time() + days * 86400
    return tok


def check_session(token):
    if not token:
        return False
    with _lock:
        exp = _sessions.get(token)
        if not exp:
            return False
        if time.time() > exp:
            _sessions.pop(token, None)
            return False
        return True


def destroy_session(token):
    with _lock:
        _sessions.pop(token, None)
