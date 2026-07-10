"""
contact_util - find how to apply to a single listing.

On explicit user action (never in bulk), fetch one listing page and pull out any
email / phone / application link. The honest truth is that most modern postings
don't expose a direct email: Craigslist routes through an anonymized relay, and
job-board listings point at an ATS form. So `kind` reports what we actually found
so the UI can react:

    email       a usable email address was found  -> can send/draft
    relay_only  Craigslist reply-relay only        -> user pastes the relay addr
    form_only   an ATS / application form          -> apply on the site
    none        nothing recognized                 -> open the listing

We deliberately do NOT try to defeat Craigslist's reply protection (captcha,
rate limits). But a ...@reply.craigslist.org address IS a real, usable inbox --
mail sent there is forwarded to the poster -- so when one is visible we keep it,
and for relay_only the composer asks the user to click reply on the listing and
paste the address themselves.
"""

import re
from urllib.parse import urlparse, unquote

import jobhunt  # for requests, UA, _MISSING_DEPS

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# US phone: optional +1, area code 2-9xx, not followed by another digit.
PHONE_RE = re.compile(
    r"(?:\+?1[\s.\-]?)?\(?([2-9]\d{2})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})(?!\d)")
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

ATS_HOSTS = (
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "workday", "indeed.com",
    "ashbyhq.com", "smartrecruiters.com", "icims.com", "jobvite.com",
    "bamboohr.com", "breezy.hr", "workable.com", "taleo.net", "ziprecruiter.com",
    "linkedin.com", "glassdoor.com", "paylocity.com", "applytojob.com",
    "jazzhr.com", "snagajob.com", "governmentjobs.com", "myworkday.com",
)
_JUNK_HOST_SUBSTR = ("wixpress", "sentry", "cloudflare", "googleapis", "gstatic",
                     "schema.org", "w3.org", "jquery", "fontawesome", "squarespace",
                     "example.com", "yourdomain", "domain.com", "email.com")
_JUNK_LOCAL = ("noreply", "no-reply", "donotreply", "do-not-reply")
_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")


def fetch_listing(url, timeout=20):
    """Fetch one listing page. Reuses jobhunt's polite UA. One call per user
    action -- callers must not loop this over many listings."""
    if jobhunt.requests is None:
        raise RuntimeError(jobhunt._MISSING_DEPS)
    r = jobhunt.requests.get(url, headers={"User-Agent": jobhunt.UA}, timeout=timeout)
    r.raise_for_status()
    return r.url, r.text


def _strip_scripts(html):
    return re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)


def _junk_email(e):
    local, _, host = e.partition("@")
    if any(e.endswith(ext) for ext in _IMG_EXT):
        return True
    if "@2x" in e or "@3x" in e:
        return True
    if local in _JUNK_LOCAL:
        return True
    if any(s in host for s in _JUNK_HOST_SUBSTR):
        return True
    return False


def _host_is_ats(host):
    return any(a in host for a in ATS_HOSTS)


def extract_contacts(html, url, source=""):
    text = _strip_scripts(html)
    hrefs = HREF_RE.findall(html)

    # --- emails: mailto links first, then anything in the visible text ---
    raw = []
    for h in hrefs:
        if h.lower().startswith("mailto:"):
            addr = unquote(h[7:].split("?", 1)[0]).strip()
            if addr:
                raw.append(addr)
    raw += EMAIL_RE.findall(text)

    emails, seen = [], set()
    for e in raw:
        e = e.strip().strip(".").lower()
        if not e or e in seen:
            continue
        seen.add(e)
        # ...@reply.craigslist.org is the poster's relay inbox -- usable as-is.
        if not e.endswith("reply.craigslist.org") and _junk_email(e):
            continue
        emails.append(e)

    # --- phones: tel links + text matches ---
    phones, pseen = [], set()
    for h in hrefs:
        if h.lower().startswith("tel:"):
            d = re.sub(r"\D", "", h[4:])
            if len(d) >= 10:
                d = d[-10:]
                p = f"({d[:3]}) {d[3:6]}-{d[6:]}"
                if p not in pseen:
                    pseen.add(p)
                    phones.append(p)
    for m in PHONE_RE.finditer(text):
        p = f"({m.group(1)}) {m.group(2)}-{m.group(3)}"
        if p not in pseen:
            pseen.add(p)
            phones.append(p)

    # --- apply url + kind ---
    host = (urlparse(url).hostname or "").lower()
    is_cl = host.endswith("craigslist.org")
    ats_link = next(
        (h for h in hrefs
         if any(a in (urlparse(h).hostname or "").lower() for a in ATS_HOSTS)),
        None)

    apply_url = url
    if emails:
        kind = "email"
    elif _host_is_ats(host):
        kind = "form_only"
    elif ats_link:
        kind, apply_url = "form_only", ats_link
    elif is_cl:
        kind = "relay_only"            # CL almost always replies via relay
    else:
        kind = "none"

    return {
        "emails": emails[:5],
        "phones": phones[:5],
        "apply_url": apply_url,
        "kind": kind,
    }


def scan(url, source=""):
    """Fetch + extract in one call. Returns the contact dict (adds the resolved
    final url under 'fetched_url')."""
    final_url, html = fetch_listing(url)
    info = extract_contacts(html, final_url, source)
    info["fetched_url"] = final_url
    return info
