#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "feedparser",
#     "requests",
# ]
# ///
"""
jobhunt - a personal job-search aggregator.

Pulls listings from Craigslist (RSS) and several other job boards, dedupes them,
scores each one against your keyword profile, and tracks where each application
stands. Everything is local: one SQLite file, one JSON config, no accounts.

Usage:
    python jobhunt.py init            # write a starter config you can edit
    python jobhunt.py fetch           # pull all sources, store new matches
    python jobhunt.py list            # show stored jobs (filters below)
    python jobhunt.py report          # build an HTML report you can open
    python jobhunt.py mark <id> <status> [--note "..."]
    python jobhunt.py stats           # pipeline counts
    python jobhunt.py seed-demo       # insert sample jobs to try it offline

Statuses: new, interested, applied, rejected, archived
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
from urllib.parse import quote_plus

# Network libs are only needed for `fetch`. Keep them optional so the web app,
# list, mark, report, etc. still run on a box without them installed.
try:
    import requests
except ImportError:
    requests = None
try:
    import feedparser
except ImportError:
    feedparser = None

_MISSING_DEPS = "needs network deps -- run: pip install feedparser requests"

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "jobhunt_config.json")
SECRETS_PATH = os.path.join(HERE, "jobhunt_secrets.json")
DB_PATH = os.path.join(HERE, "jobhunt.db")
REPORT_PATH = os.path.join(HERE, "jobhunt_report.html")
UA = "jobhunt-personal/1.0 (personal job search; respectful polling)"
STATUSES = ["new", "interested", "applied", "rejected", "archived"]

DEFAULT_CONFIG = {
    "profile": {
        # term -> points added if it appears anywhere in the listing
        "keywords_positive": {
            "summer": 6, "seasonal": 5, "part-time": 5, "part time": 5,
            "no experience": 6, "entry level": 5, "entry-level": 5,
            "barista": 4, "cashier": 4, "retail": 3, "host": 3, "server": 3,
            "crew": 3, "scooper": 4, "ice cream": 3, "camp": 5, "counselor": 4,
            "lifeguard": 4, "tutor": 4, "intern": 4, "internship": 4,
            "student": 3, "weekend": 2, "flexible": 2, "training provided": 4,
        },
        # term -> points subtracted (soft penalty; still shown, just ranked lower)
        "keywords_negative": {
            "manager": -6, "supervisor": -4, "experience required": -6,
            "years experience": -6, "full-time only": -4, "overnight": -3,
        },
        # HARD exclude: a listing containing any of these is dropped entirely.
        # These get merged with whatever is in exclude_file (see below).
        "exclude": [],
        # Import an exclude list from a plain text file (one term per line,
        # '#' starts a comment). Path is relative to this script.
        "exclude_file": "exclude_keywords.txt",
        # if non-empty, a listing is dropped unless it contains one of these
        "must_have": [],
        # extra points when a positive keyword appears in the title specifically
        "title_boost": 3,
        # listings scoring below this are hidden from list/report (kept in db)
        "min_display_score": 1,
    },

    # Keep jobs that are walkable from home or a reasonable transit ride; drop
    # the rest. Matching is done on the listing's location/title/summary text.
    "location_filter": {
        "enabled": True,
        "home": "Davis Square, Somerville, MA",
        "remote_ok": True,          # treat 'remote' listings as acceptable
        "drop_unmatched": False,    # True = also drop listings with no recognizable location
        "walkable_bonus": 8,        # added when a 'walkable' area is mentioned
        "transit_bonus": 3,         # added when an 'allow' area is mentioned
        # Short walk / one Red Line stop from Davis -- ranked highest.
        "walkable": [
            "davis", "teele", "ball square", "magoun", "west somerville",
            "tufts", "powderhouse", "college ave", "porter"
        ],
        # Reasonable on the T (Red Line, key buses, Green Line Extension).
        "allow": [
            "somerville", "porter", "north cambridge", "cambridge", "harvard",
            "central square", "kendall", "mit", "alewife", "medford",
            "arlington", "union square", "inman", "east cambridge", "lechmere",
            "charlestown", "boston", "downtown", "downtown crossing",
            "south station", "back bay", "beacon hill", "financial district",
            "fenway", "allston", "brighton", "malden", "everett", "chelsea",
            "remote"
        ],
        # Too far / effectively car-dependent from Davis -- dropped.
        "block": [
            "burlington", "woburn", "wilmington", "billerica", "lexington",
            "bedford", "waltham", "framingham", "natick", "needham", "dedham",
            "marlborough", "peabody", "danvers", "saugus", "andover", "lowell",
            "nashua", "new hampshire", "worcester", "brockton", "plymouth",
            "cape cod", "providence", "rhode island", "south shore",
            "north shore", "metrowest", "braintree", "weymouth", "quincy",
            "salem", "gloucester"
        ]
    },

    "sources": {
        "craigslist": {
            "enabled": True,
            "request_delay_seconds": 3,
            "searches": [
                {"city": "boston", "category": "jjj", "query": "summer"},
                {"city": "boston", "category": "jjj", "query": "part time"},
                {"city": "boston", "category": "jjj", "query": "no experience"},
                {"city": "boston", "category": "jjj", "query": "barista"},
                {"city": "boston", "category": "jjj", "query": "camp counselor"},
                {"city": "boston", "category": "ggg", "query": "summer"}
            ]
        },
        # Remote tech boards -- off by default (not relevant for a local
        # summer job). Flip enabled to true if you also want remote gigs.
        "remoteok": {"enabled": False, "tags": []},
        "remotive": {"enabled": False, "search": "", "category": ""},
        "weworkremotely": {"enabled": False, "feeds": []},

        # Best source for local listings with real distance filtering.
        # Get free keys at https://developer.adzuna.com/ , paste them below.
        "adzuna": {
            "enabled": True, "app_id": "", "app_key": "", "country": "us",
            "what": "part time summer", "where": "Somerville, Massachusetts",
            "distance": 13, "max_days_old": 30, "sort_by": "date",
            "results_per_page": 50, "pages": 3, "request_delay_seconds": 1
        }
    },

    # Who you are -- used as the From identity and to fill the cover note when you
    # apply from the app. (Email login/password live separately in
    # jobhunt_secrets.json so they never end up in this shareable file.)
    "applicant": {"name": "", "email": "", "phone": ""},

    # The cover message sent/drafted with your resume. Placeholders {name},
    # {job_title}, {company}, {my_email}, {my_phone} are filled per listing.
    "outreach": {
        "cover_template": (
            "Hi,\n\n"
            "I'm writing to apply for the {job_title} position"
            " at {company}. I'm a local, reliable, and eager to learn, and I think"
            " I'd be a great fit. My resume is attached -- I'd love to talk about"
            " the role whenever works for you.\n\n"
            "Thanks for your time,\n"
            "{name}\n"
            "{my_email} | {my_phone}\n"
        )
    }
}


# --------------------------------------------------------------------------- #
# Config / DB plumbing
# --------------------------------------------------------------------------- #
def read_terms_file(path):
    """One term per line; '#' starts a comment; blanks ignored. Returns lowercased."""
    terms = []
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                term = line.split("#", 1)[0].strip().lower()
                if term:
                    terms.append(term)
    return terms


def exclude_file_path(cfg):
    """Absolute path to the configured exclude-keywords text file."""
    ef = cfg.get("profile", {}).get("exclude_file")
    if ef and not os.path.isabs(ef):
        ef = os.path.join(HERE, ef)
    return ef


def load_config(merge_excludes=True):
    """Load the JSON config. By default the exclude-keywords file is merged into
    profile['exclude'] (what scoring needs). Pass merge_excludes=False to get the
    raw on-disk config -- use that when you intend to edit and save it back, so
    file-sourced excludes don't get baked into the inline list."""
    if not os.path.exists(CONFIG_PATH):
        sys.exit(f"No config found. Run:  python {os.path.basename(__file__)} init")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if merge_excludes:
        prof = cfg.get("profile", {})
        inline = [t.lower() for t in prof.get("exclude", [])]
        prof["exclude"] = sorted(set(inline) | set(read_terms_file(exclude_file_path(cfg))))
        cfg["profile"] = prof
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_secrets():
    """SMTP credentials live in a separate file so they never land in the main
    config (which is meant to be readable/shareable). Returns {} if absent."""
    if os.path.exists(SECRETS_PATH):
        try:
            with open(SECRETS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_secrets(secrets):
    with open(SECRETS_PATH, "w", encoding="utf-8") as f:
        json.dump(secrets, f, indent=2)
    try:
        os.chmod(SECRETS_PATH, 0o600)   # best-effort: keep creds owner-only
    except OSError:
        pass


# Columns added after the original schema; (name, sql-type) applied via ALTER.
_JOB_EXTRA_COLUMNS = [
    ("contact_email", "TEXT"),
    ("contact_phone", "TEXT"),
    ("contact_apply_url", "TEXT"),
    ("contact_kind", "TEXT"),
    ("contact_fetched_at", "TEXT"),
]


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            source      TEXT,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            url         TEXT,
            summary     TEXT,
            posted      TEXT,
            first_seen  TEXT,
            score       INTEGER,
            status      TEXT DEFAULT 'new',
            note        TEXT DEFAULT '',
            applied_at  TEXT
        )
    """)
    # Lightweight migration: add contact columns to existing dbs if missing.
    have = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    for name, ctype in _JOB_EXTRA_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ctype}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT,
            method      TEXT,
            to_addr     TEXT,
            subject     TEXT,
            body        TEXT,
            attachment  TEXT,
            status      TEXT,
            error       TEXT,
            created_at  TEXT
        )
    """)
    conn.commit()
    return conn


def job_id(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def has_term(term, text):
    """True if `term` appears in `text` as a whole token, not buried inside a
    larger word. Both are assumed lowercase. Word-boundary matching keeps
    'camp' out of 'campus', 'intern' out of 'international', and a bare wage
    like '$21+/hour' from tripping a '21+' exclude."""
    if not term:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])",
                     text) is not None


def score_job(job, profile, locf=None):
    title = (job.get("title") or "").lower()
    hay = " ".join(str(job.get(k) or "") for k in
                   ("title", "company", "location", "summary")).lower()
    # Location is matched only against the listing's own location/title fields,
    # never the free-text summary -- otherwise a Davis job that merely mentions
    # "our Burlington branch" would be dropped or mis-scored.
    loc_hay = " ".join(str(job.get(k) or "") for k in
                       ("location", "title")).lower()

    # Hard exclude: any blocked keyword drops the listing entirely.
    for term in profile.get("exclude", []):
        if has_term(term.lower(), hay):
            return None

    # Optional must-have filter.
    must = [m.lower() for m in profile.get("must_have", [])]
    if must and not any(has_term(m, hay) for m in must):
        return None

    # Location filter.
    loc_bonus = 0
    if locf and locf.get("enabled"):
        if any(has_term(b.lower(), loc_hay) for b in locf.get("block", [])):
            return None  # too far / car-dependent
        walk = [w.lower() for w in locf.get("walkable", [])]
        allow = [a.lower() for a in locf.get("allow", [])]
        is_walk = any(has_term(w, loc_hay) for w in walk)
        is_allow = is_walk or any(has_term(a, loc_hay) for a in allow)
        if locf.get("remote_ok") and has_term("remote", loc_hay):
            is_allow = True
        if not is_allow and locf.get("drop_unmatched"):
            return None
        loc_bonus = (locf.get("walkable_bonus", 8) if is_walk
                     else locf.get("transit_bonus", 3) if is_allow else 0)

    score = loc_bonus
    boost = profile.get("title_boost", 0)
    for term, pts in profile.get("keywords_positive", {}).items():
        t = term.lower()
        if has_term(t, hay):
            score += pts
            if has_term(t, title):
                score += boost
    for term, pts in profile.get("keywords_negative", {}).items():
        if has_term(term.lower(), hay):
            score += pts  # pts is already negative
    return score


# --------------------------------------------------------------------------- #
# Sources -- each returns a list of normalized dicts:
#   {source, title, company, location, url, summary, posted}
# --------------------------------------------------------------------------- #
def fetch_feed(url):
    if feedparser is None:
        raise RuntimeError(_MISSING_DEPS)
    return feedparser.parse(url, request_headers={"User-Agent": UA})


def get_json(url, params=None):
    if requests is None:
        raise RuntimeError(_MISSING_DEPS)
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    return r.json()


# Craigslist killed its RSS search feed (?format=rss now 403s for everyone), so we
# parse the no-JS HTML search page instead. Each result is a <li> like:
#   <li class="cl-static-search-result" title="...">
#     <a href="...html"><div class="title">...</div>
#       <div class="details"><div class="price">..</div>
#         <div class="location">somerville</div></div></a></li>
_CL_BLOCK_RE = re.compile(r'<li class="cl-static-search-result".*?</li>', re.S)
_CL_HREF_RE = re.compile(r'<a[^>]+href="([^"]+)"')
_CL_TITLE_RE = re.compile(r'<div class="title">(.*?)</div>', re.S)
_CL_LOC_RE = re.compile(r'<div class="location">\s*(.*?)\s*</div>', re.S)


def src_craigslist(cfg):
    if requests is None:
        raise RuntimeError(_MISSING_DEPS)
    out, delay = [], cfg.get("request_delay_seconds", 3)
    for s in cfg.get("searches", []):
        city, cat = s["city"], s.get("category", "jjj")
        q = quote_plus(s.get("query", ""))
        url = f"https://{city}.craigslist.org/search/{cat}?query={q}"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        for block in _CL_BLOCK_RE.findall(r.text):
            mu = _CL_HREF_RE.search(block)
            if not mu:
                continue
            mt = _CL_TITLE_RE.search(block)
            ml = _CL_LOC_RE.search(block)
            out.append({
                "source": f"craigslist/{city}",
                "title": html.unescape(mt.group(1).strip()) if mt else "",
                "company": "",
                "location": html.unescape(ml.group(1).strip()) if ml else city,
                "url": mu.group(1),
                "summary": "",          # the listing body is on the posting page
                "posted": "",
            })
        time.sleep(delay)  # be polite; CL blocks aggressive pollers
    return out


def src_remoteok(cfg):
    data = get_json("https://remoteok.com/api")
    wanted = [t.lower() for t in cfg.get("tags", [])]
    out = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is legal/metadata
        tags = [t.lower() for t in j.get("tags", [])]
        if wanted and not any(w in tags for w in wanted):
            continue
        out.append({
            "source": "remoteok",
            "title": j.get("position", ""),
            "company": j.get("company", ""),
            "location": j.get("location", "Remote"),
            "url": j.get("url", ""),
            "summary": j.get("description", ""),
            "posted": j.get("date", ""),
        })
    return out


def src_remotive(cfg):
    params = {}
    if cfg.get("search"):
        params["search"] = cfg["search"]
    if cfg.get("category"):
        params["category"] = cfg["category"]
    data = get_json("https://remotive.com/api/remote-jobs", params=params)
    out = []
    for j in data.get("jobs", []):
        out.append({
            "source": "remotive",
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location", "Remote"),
            "url": j.get("url", ""),
            "summary": j.get("description", ""),
            "posted": j.get("publication_date", ""),
        })
    return out


def src_weworkremotely(cfg):
    out = []
    for url in cfg.get("feeds", []):
        feed = fetch_feed(url)
        for e in feed.entries:
            title = e.get("title", "")
            company, _, role = title.partition(": ")
            out.append({
                "source": "weworkremotely",
                "title": role or title,
                "company": company if role else "",
                "location": "Remote",
                "url": e.get("link", ""),
                "summary": e.get("summary", ""),
                "posted": e.get("published", ""),
            })
    return out


def src_adzuna(cfg):
    if not cfg.get("app_id") or not cfg.get("app_key"):
        print("  adzuna: add free app_id/app_key to config for local distance "
              "filtering (https://developer.adzuna.com/) -- skipping")
        return []
    country = cfg.get("country", "us")
    per_page = cfg.get("results_per_page", 50)
    pages = max(1, cfg.get("pages", 1))               # how many result pages to pull
    delay = cfg.get("request_delay_seconds", 1)
    base_params = {
        "app_id": cfg["app_id"], "app_key": cfg["app_key"],
        "what": cfg.get("what", ""), "where": cfg.get("where", ""),
        "results_per_page": per_page,
        "content-type": "application/json",
    }
    if cfg.get("distance"):
        base_params["distance"] = cfg["distance"]     # km radius around 'where'
    if cfg.get("max_days_old"):
        base_params["max_days_old"] = cfg["max_days_old"]
    if cfg.get("sort_by"):
        base_params["sort_by"] = cfg["sort_by"]

    out = []
    for page in range(1, pages + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        data = get_json(url, params=base_params)
        results = data.get("results", [])
        for j in results:
            out.append({
                "source": "adzuna",
                "title": j.get("title", ""),
                "company": (j.get("company") or {}).get("display_name", ""),
                "location": (j.get("location") or {}).get("display_name", ""),
                "url": j.get("redirect_url", ""),
                "summary": j.get("description", ""),
                "posted": j.get("created", ""),
            })
        if len(results) < per_page:
            break                                     # last page reached
        if page < pages:
            time.sleep(delay)                         # be polite between pages
    return out


SOURCES = {
    "craigslist": src_craigslist,
    "remoteok": src_remoteok,
    "remotive": src_remotive,
    "weworkremotely": src_weworkremotely,
    "adzuna": src_adzuna,
}


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_init(_):
    if os.path.exists(CONFIG_PATH):
        print(f"Config already exists at {CONFIG_PATH} (leaving it alone).")
        return
    with open(CONFIG_PATH, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"Wrote starter config to {CONFIG_PATH}")
    print("Edit it: set your cities, queries, and keyword weights, then run 'fetch'.")


def fetch_jobs(conn, cfg, on_progress=None):
    """Pull every enabled source, store new scored matches, and return a summary
    dict: {total_new, per_source: {name: count|error}, top: [(score,source,title,id)]}.
    `on_progress(name, msg)` is called per source if provided (used by the CLI/web
    layer to stream progress)."""
    profile = cfg["profile"]
    locf = cfg.get("location_filter")
    now = dt.datetime.now().isoformat(timespec="seconds")
    total_new, fresh_top, per_source = 0, [], {}

    for name, scfg in cfg["sources"].items():
        if not scfg.get("enabled"):
            continue
        fn = SOURCES.get(name)
        if not fn:
            per_source[name] = "no handler"
            continue
        try:
            jobs = fn(scfg)
        except Exception as e:
            per_source[name] = f"ERROR {e}"
            if on_progress:
                on_progress(name, f"ERROR {e}")
            continue

        new_here = 0
        for j in jobs:
            if not j.get("url"):
                continue
            jid = job_id(j["url"])
            if conn.execute("SELECT 1 FROM jobs WHERE id=?", (jid,)).fetchone():
                continue
            sc = score_job(j, profile, locf)
            if sc is None:  # failed exclude / location / must_have filter
                continue
            conn.execute(
                """INSERT INTO jobs
                   (id, source, title, company, location, url, summary,
                    posted, first_seen, score, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?, 'new')""",
                (jid, j["source"], j["title"], j["company"], j["location"],
                 j["url"], j["summary"], j["posted"], now, sc))
            new_here += 1
            fresh_top.append((sc, j["source"], j["title"], jid))
        per_source[name] = new_here
        total_new += new_here
        if on_progress:
            on_progress(name, f"{new_here} new")

    conn.commit()
    fresh_top.sort(reverse=True)
    return {"total_new": total_new, "per_source": per_source, "top": fresh_top[:10]}


def cmd_fetch(_):
    cfg = load_config()
    conn = db()
    summary = fetch_jobs(conn, cfg,
                         on_progress=lambda name, msg: print(f"  {name}: {msg}"))
    print(f"\n{summary['total_new']} new listings stored.")
    if summary["top"]:
        print("\nTop new matches:")
        for sc, source, title, jid in summary["top"]:
            print(f"  [{sc:>3}] {jid}  {title[:60]:<60}  ({source})")


def cmd_list(args):
    cfg = load_config()
    conn = db()
    q = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if args.status:
        q += " AND status=?"
        params.append(args.status)
    min_score = (args.min_score if args.min_score is not None
                 else cfg["profile"].get("min_display_score", 0))
    q += " AND score >= ?"
    params.append(min_score)
    q += " ORDER BY score DESC, first_seen DESC LIMIT ?"
    params.append(args.limit)

    rows = conn.execute(q, params).fetchall()
    if not rows:
        print("No matching jobs.")
        return
    for r in rows:
        print(f"[{r['score']:>3}] {r['id']}  {r['status']:<10} "
              f"{(r['title'] or '')[:55]:<55}  {r['source']}")
        if r['company'] or r['location']:
            print(f"        {r['company']}  |  {r['location']}")
        print(f"        {r['url']}")


def cmd_mark(args):
    if args.status not in STATUSES:
        sys.exit(f"Status must be one of: {', '.join(STATUSES)}")
    conn = db()
    row = conn.execute("SELECT id FROM jobs WHERE id=?", (args.id,)).fetchone()
    if not row:
        sys.exit(f"No job with id {args.id}")
    applied_at = (dt.datetime.now().isoformat(timespec="seconds")
                  if args.status == "applied" else None)
    if args.note is not None:
        conn.execute("UPDATE jobs SET status=?, note=?, applied_at=COALESCE(?, applied_at) WHERE id=?",
                     (args.status, args.note, applied_at, args.id))
    else:
        conn.execute("UPDATE jobs SET status=?, applied_at=COALESCE(?, applied_at) WHERE id=?",
                     (args.status, applied_at, args.id))
    conn.commit()
    print(f"{args.id} -> {args.status}")


def cmd_stats(_):
    conn = db()
    rows = conn.execute(
        "SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(f"{total} jobs total")
    for r in rows:
        print(f"  {r['status']:<12} {r['n']}")


def cmd_report(_):
    cfg = load_config()
    conn = db()
    min_score = cfg["profile"].get("min_display_score", 0)
    rows = conn.execute(
        "SELECT * FROM jobs WHERE score >= ? AND status NOT IN ('rejected','archived') "
        "ORDER BY score DESC, first_seen DESC", (min_score,)).fetchall()

    badge = {"new": "#2563eb", "interested": "#7c3aed",
             "applied": "#059669", "rejected": "#dc2626", "archived": "#6b7280"}
    cards = []
    for r in rows:
        summary = html.escape((r["summary"] or "")[:280])
        cards.append(f"""
        <tr>
          <td class="score">{r['score']}</td>
          <td>
            <a href="{html.escape(r['url'] or '#')}" target="_blank">{html.escape(r['title'] or '')}</a>
            <div class="meta">{html.escape(r['company'] or '')} &middot; {html.escape(r['location'] or '')} &middot; {html.escape(r['source'])}</div>
            <div class="summary">{summary}</div>
          </td>
          <td><span class="badge" style="background:{badge.get(r['status'],'#888')}">{r['status']}</span>
              <div class="meta">{html.escape(r['id'])}</div></td>
        </tr>""")

    page = f"""<!doctype html><meta charset="utf-8">
<title>jobhunt report</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; max-width: 960px; margin: 2rem auto; color:#111; padding:0 1rem; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ width:100%; border-collapse: collapse; }}
  td {{ border-bottom:1px solid #eee; padding:.75rem .5rem; vertical-align:top; }}
  .score {{ font-weight:700; font-size:1.1rem; width:3rem; text-align:center; color:#2563eb; }}
  .meta {{ color:#666; font-size:.82rem; margin-top:.2rem; }}
  .summary {{ color:#333; font-size:.85rem; margin-top:.3rem; }}
  .badge {{ color:#fff; padding:.1rem .5rem; border-radius:1rem; font-size:.75rem; }}
  a {{ color:#1d4ed8; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
</style>
<h1>jobhunt &mdash; {len(rows)} active listings</h1>
<p class="meta">Generated {dt.datetime.now():%Y-%m-%d %H:%M}. Sorted by fit score. Rejected/archived hidden.</p>
<table>{''.join(cards)}</table>"""

    with open(REPORT_PATH, "w") as f:
        f.write(page)
    print(f"Wrote {REPORT_PATH}")


def cmd_seed_demo(_):
    """Insert a few fake jobs so you can see scoring/tracking before configuring."""
    if not os.path.exists(CONFIG_PATH):
        cmd_init(None)
    cfg = load_config()
    conn = db()
    now = dt.datetime.now().isoformat(timespec="seconds")
    locf = cfg.get("location_filter")
    demo = [
        {"source": "craigslist/boston", "title": "Summer Barista - Part Time (Davis Square)",
         "company": "Diesel Cafe", "location": "Davis Square, Somerville",
         "url": "https://example.com/job/1",
         "summary": "Seasonal part-time barista, no experience needed, training provided.",
         "posted": now},
        {"source": "craigslist/boston", "title": "Delivery Driver - must have own car",
         "company": "QuickEats", "location": "Boston",
         "url": "https://example.com/job/2",
         "summary": "Reliable vehicle required. Valid driver's license required.",
         "posted": now},
        {"source": "craigslist/boston", "title": "Camp Counselor - Summer Day Camp",
         "company": "Arlington Rec", "location": "Arlington, MA",
         "url": "https://example.com/job/3",
         "summary": "Summer camp counselor, entry level, weekdays.",
         "posted": now},
        {"source": "adzuna", "title": "Retail Sales Associate",
         "company": "Mall Store", "location": "Burlington, MA",
         "url": "https://example.com/job/4",
         "summary": "Part time retail position at the Burlington Mall.",
         "posted": now},
        {"source": "adzuna", "title": "Senior Account Manager",
         "company": "BigCorp", "location": "Boston",
         "url": "https://example.com/job/5",
         "summary": "5+ years experience required. Full-time only.",
         "posted": now},
    ]
    n = 0
    for j in demo:
        jid = job_id(j["url"])
        if conn.execute("SELECT 1 FROM jobs WHERE id=?", (jid,)).fetchone():
            continue
        sc = score_job(j, cfg["profile"], locf)
        if sc is None:
            continue
        conn.execute(
            """INSERT INTO jobs (id, source, title, company, location, url, summary,
               posted, first_seen, score, status) VALUES (?,?,?,?,?,?,?,?,?,?, 'new')""",
            (jid, j["source"], j["title"], j["company"], j["location"],
             j["url"], j["summary"], j["posted"], now, sc))
        n += 1
    conn.commit()
    print(f"Seeded {n} demo jobs. Try:  python {os.path.basename(__file__)} list")


def cmd_serve(args):
    if not os.path.exists(CONFIG_PATH):
        cmd_init(None)
    import jobhunt_web
    jobhunt_web.serve(host=args.host, port=args.port, open_browser=not args.no_open)


def main():
    p = argparse.ArgumentParser(description="Personal job-search aggregator")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("fetch").set_defaults(func=cmd_fetch)
    sub.add_parser("report").set_defaults(func=cmd_report)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("seed-demo").set_defaults(func=cmd_seed_demo)

    ps = sub.add_parser("serve", help="run the local web app (keyword editor + map)")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8765)
    ps.add_argument("--no-open", action="store_true", help="don't open a browser")
    ps.set_defaults(func=cmd_serve)

    pl = sub.add_parser("list")
    pl.add_argument("--status", choices=STATUSES)
    pl.add_argument("--min-score", type=int)
    pl.add_argument("--limit", type=int, default=25)
    pl.set_defaults(func=cmd_list)

    pm = sub.add_parser("mark")
    pm.add_argument("id")
    pm.add_argument("status")
    pm.add_argument("--note")
    pm.set_defaults(func=cmd_mark)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
