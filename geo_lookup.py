"""
geo_lookup - place a job on the map, trying cheap and local before slow and
remote, so the radius filter can tell how far away every listing really is.

Resolution order for a job (first hit wins):
  1. geo_data.resolve      -- the fine-grained Davis-area gazetteer (offline)
  2. geo_data.town_lookup  -- every Massachusetts municipality (offline)
  3. Nominatim: location   -- OpenStreetMap's free geocoder, for street
                              addresses and out-of-state places
  4. Nominatim: company    -- last resort when the location text says nothing:
                              look the business up by name near home; for
                              chains, the branch nearest home is used

Results land on the job row (lat/lng/geo_matched/geo_source) at fetch time,
and a backfill sweeps rows fetched before this existed -- the radius slider
only ever compares stored coordinates.

Nominatim etiquette: at most one request per second, a descriptive User-Agent,
and every answer (including "not found") cached in the geo_cache table so no
query is ever repeated. Online lookups can be turned off entirely with
{"geocoding": {"online": false}} in the config.
"""

import datetime as dt
import re
import threading
import time

import requests

import geo_data

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "jobhunt/1.0 (personal local job search)"}
MIN_INTERVAL = 1.1                  # seconds between Nominatim calls

# Bias box around home, roughly 45 miles a side: company-name searches are
# restricted to it (a bare brand name must not match a store in Ohio);
# location-text searches merely prefer it.
_BOX = 0.65
VIEWBOX = (f"{geo_data.HOME['lng'] - _BOX},{geo_data.HOME['lat'] + _BOX * 0.75},"
           f"{geo_data.HOME['lng'] + _BOX},{geo_data.HOME['lat'] - _BOX * 0.75}")

_lock = threading.Lock()
_last_call = [0.0]


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _cache_get(conn, query):
    row = conn.execute("SELECT * FROM geo_cache WHERE query=?", (query,)).fetchone()
    if not row:
        return None
    if not row["found"]:
        return {"found": False}
    return {"found": True, "lat": row["lat"], "lng": row["lng"],
            "matched": row["matched"]}


def _cache_put(conn, query, hit):
    conn.execute(
        "INSERT OR REPLACE INTO geo_cache (query, lat, lng, matched, found, checked_at)"
        " VALUES (?,?,?,?,?,?)",
        (query, hit and hit["lat"], hit and hit["lng"], hit and hit["matched"],
         1 if hit else 0, _now()))
    conn.commit()


def _nominatim(params):
    """One rate-limited Nominatim request. Returns the parsed result list.
    Raises on network trouble -- callers treat that as 'try again later'."""
    with _lock:
        wait = MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
    r = requests.get(NOMINATIM, params=params, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def _nearest(results):
    """The result closest to home, as {lat, lng, matched}."""
    best, best_d = None, None
    for res in results:
        try:
            lat, lng = float(res["lat"]), float(res["lon"])
        except (KeyError, ValueError):
            continue
        d = geo_data.miles_from_home(lat, lng)
        if best is None or d < best_d:
            best, best_d = {"lat": lat, "lng": lng,
                            "matched": (res.get("display_name") or "").split(",")[0].lower()}, d
    return best


def lookup_place(conn, location_text):
    """Geocode free-form location text ("15 Main St, Woburn", "Salem NH").
    Cached; returns {lat, lng, matched} or None."""
    q = " ".join((location_text or "").split())[:120]
    if len(q) < 3:
        return None
    if not re.search(r"\b(ma|mass|massachusetts|nh|ri)\b", q.lower()):
        q += ", MA"
    key = "place:" + q.lower()
    cached = _cache_get(conn, key)
    if cached is not None:
        return cached if cached["found"] else None
    results = _nominatim({"q": q, "format": "jsonv2", "limit": 3,
                          "countrycodes": "us", "viewbox": VIEWBOX})
    hit = _nearest(results)
    # A query that says Massachusetts cannot honestly resolve 130+ miles from
    # home (the whole state fits inside that). Such a hit is the geocoder
    # matching a namesake in another state ("Southshore MA" -> a Texas
    # lakefront); better to record "not found" than confident wrong coords.
    if (hit and re.search(r"\b(ma|mass|massachusetts)\b", q.lower())
            and geo_data.miles_from_home(hit["lat"], hit["lng"]) > 130):
        hit = None
    _cache_put(conn, key, hit)
    return hit


def lookup_company(conn, company):
    """Find a business by name near home (viewbox-bounded so a bare brand name
    can't match a namesake across the country). For chains, the nearest branch.
    Cached; returns {lat, lng, matched} or None."""
    q = " ".join((company or "").split())[:80]
    if len(q) < 3:
        return None
    key = "company:" + q.lower()
    cached = _cache_get(conn, key)
    if cached is not None:
        return cached if cached["found"] else None
    results = _nominatim({"q": q, "format": "jsonv2", "limit": 5,
                          "countrycodes": "us", "viewbox": VIEWBOX, "bounded": 1})
    hit = _nearest(results)
    _cache_put(conn, key, hit)
    return hit


def company_distance(conn, company):
    """Distance in miles from home to a company's nearest location, or None."""
    hit = lookup_company(conn, company)
    return round(geo_data.miles_from_home(hit["lat"], hit["lng"]), 1) if hit else None


def resolve_job(conn, location, title, company, online=True):
    """Run the full resolution ladder. Returns
    {lat, lng, matched, source, remote} -- lat/lng may be None (remote or
    truly unknown). Raises only on network errors from the online steps."""
    hit = geo_data.resolve(location, title)
    if hit and hit["lat"] is not None:
        return {**hit, "source": "area"}
    remote = bool(hit and hit["remote"])

    town = geo_data.town_lookup(location, title)
    if town:
        return {**town, "remote": remote or town["remote"], "source": "town"}

    if online and not remote:
        place = lookup_place(conn, location)
        if place:
            return {"lat": place["lat"], "lng": place["lng"],
                    "matched": place["matched"], "remote": False, "source": "osm"}
        biz = lookup_company(conn, company)
        if biz:
            return {"lat": biz["lat"], "lng": biz["lng"],
                    "matched": biz["matched"], "remote": False, "source": "company"}

    return {"lat": None, "lng": None, "matched": "remote" if remote else None,
            "remote": remote, "source": "none"}


def backfill(conn, cfg=None, on_progress=None):
    """Resolve every job row that hasn't been through the ladder yet
    (geo_checked_at IS NULL). Offline steps always run; online steps respect
    the config toggle. A row is only stamped checked when its lookup finished,
    so a network failure just means it's retried next sweep. Returns counts."""
    online = True
    if cfg is not None:
        online = bool(cfg.get("geocoding", {}).get("online", True))
    rows = conn.execute(
        "SELECT id, location, title, company FROM jobs"
        " WHERE geo_checked_at IS NULL").fetchall()
    placed = unknown = failed = 0
    for r in rows:
        try:
            geo = resolve_job(conn, r["location"], r["title"], r["company"], online)
        except Exception:                        # noqa: BLE001 -- network hiccup
            failed += 1
            continue
        conn.execute(
            "UPDATE jobs SET lat=?, lng=?, geo_matched=?, geo_source=?,"
            " geo_remote=?, geo_checked_at=? WHERE id=?",
            (geo["lat"], geo["lng"], geo["matched"], geo["source"],
             1 if geo["remote"] else 0, _now(), r["id"]))
        conn.commit()
        if geo["lat"] is not None:
            placed += 1
        else:
            unknown += 1
        if on_progress and (placed + unknown) % 25 == 0:
            on_progress(f"geo backfill: {placed + unknown}/{len(rows)}")
    return {"placed": placed, "unknown": unknown, "failed": failed,
            "total": len(rows)}
