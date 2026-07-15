# jobhunt — extras & customization

Everything that isn't needed day-to-day. For launching, using, applying, and
updating, see the [README](README.md).

---

## How the scoring works

Every listing passes three gates, then gets a **fit score**:

1. **Hard exclude** — drops anything containing a term in `exclude_keywords.txt`
   (ships with age limits, car/driving requirements, too-senior roles, and scams).
   Add terms in the **Exclude** box in the app to hide matching jobs **instantly** —
   no refetch needed.
2. **Location filter** — keeps places reachable on the T around Davis Square, drops
   far/car-dependent towns, and gives a bonus to walkable spots (Davis, Teele, Ball
   Square, Tufts, Porter).
3. **Must-have** (optional) — require a term to appear.

What survives is scored: positive keywords (`summer`, `part time`, `barista`,
`camp`, …) add points, a walkable/transit bonus is added, and soft-negative keywords
(`manager`, `experience required`) push weaker matches down. Tune all of this live in
the app, or in `jobhunt_config.json`.

**Full-text pass:** Craigslist search results only include titles, so after each
fetch the app politely reads the posting pages of the top new Craigslist results
(up to `body_fetch_limit`, default 25, one page at a time with a delay). Scores —
and your exclude keywords — then apply to the **full ad text**, and pay is picked
up when the poster listed it. A listing whose full text trips a filter is archived
automatically.

---

## Job sources

| Source | On by default | Key needed? |
|---|---|---|
| **Craigslist** (Boston) | ✅ yes | no |
| **Adzuna** (local distance filtering) | enabled, but idle until you add free keys | yes (free) |
| **Jooble** (local aggregator, different inventory) | enabled, but idle until you add a free key | yes (free) |
| RemoteOK / Remotive / We Work Remotely | off (remote-tech jobs) | no |

To add more local listings, get free keys at <https://developer.adzuna.com/> and/or
<https://jooble.org/api/about> and paste them into the `adzuna` / `jooble` sections
of `jobhunt_config.json`.

---

## How jobs get placed on the map

Each listing is placed once, at fetch time, trying cheap and local before slow
and remote: the Davis-area gazetteer, then a built-in table of all 351
Massachusetts municipalities, then OpenStreetMap's free Nominatim geocoder for
street addresses — and as a last resort the **company name** is looked up near
home (for chains, the nearest branch). Results are cached in the database, and
online lookups are throttled to one per second. To keep everything strictly
offline, add `"geocoding": {"online": false}` to `jobhunt_config.json` — town
names still resolve from the built-in table.

With the **radius filter on**, listings whose location can't be determined at
all are hidden (remote jobs stay); the count line under the slider says how
many were hidden and why.

---

## Run it in Docker (Linux)

Prefer a container? There's a Dockerfile and Compose setup. You need Docker with
the Compose plugin, and you should run it on a **home machine** — Craigslist
blocks datacenter/VPN IPs, so a cloud host won't fetch listings.

```bash
./start-jobhunt-docker.sh     # build + run; prints the URL
./logs-jobhunt-docker.sh      # watch what it's doing
./stop-jobhunt-docker.sh      # stop (data kept)
./update-jobhunt-docker.sh    # git pull + rebuild to the latest version
```

Or drive Compose yourself: `docker compose up -d --build`.

- **Your data lives in `./data`** (db, config, email login, resumes, exclude
  list) — bind-mounted into the container, so rebuilds never touch it. Back it
  up by copying that folder. The start script runs the container as your user,
  so the files aren't root-owned.
- **The app is published on `0.0.0.0:8765`** — reachable from your phone at
  `http://<your-ip>:8765`. There's no password, so only do this on Wi-Fi you
  trust; for this-machine-only, change the port line in `docker-compose.yml` to
  `"127.0.0.1:8765:8765"`. You may also need to allow port 8765 through the host
  firewall for other devices to connect.
- **Updates:** the in-app self-updater is disabled in the container (the sidebar
  shows "container · update by rebuilding the image"). Update with
  `./update-jobhunt-docker.sh`, which pulls the latest code and rebuilds.
- **Data location** is controlled by the `JOBHUNT_DATA_DIR` env var (set to
  `/data` in the image); a normal non-Docker install ignores it and keeps data
  beside the code as before.

---

## Change the area

Everything about location lives in `jobhunt_config.json` under `location_filter`
(swap the `walkable` / `allow` / `block` neighborhood lists and the `home`), the
Craigslist `searches`, and `geo_data.py` (the map's coordinates and transit lines).

---

## Use it from your phone (Windows)

On **Windows**, the start file also makes the app reachable from other devices on the
same Wi-Fi — handy for browsing jobs from the couch. The very first time, Windows may
show a **User Account Control** prompt asking to allow a firewall change; click **Yes**
(this is a one-time rule that lets your phone reach the app, and it only happens once).

The little window then prints an address like `http://192.168.x.x:8765` — type that
into your phone's browser while the app is running on the PC.

> There's no password on the app, so anyone on your home Wi-Fi could open it. That's
> normally fine at home; on shared or public Wi-Fi, don't use this. On Mac and Linux
> the app stays private to that computer.

---

## Updating — start clean in a new folder

Normally you never need this — jobhunt updates itself from inside the app (the
green **⬆ Update** button; see the [README](README.md#-updating-to-a-new-version)).
But if you want a totally fresh copy (say things feel broken), download the repo
zip from GitHub (green **Code** button → Download ZIP), unzip it into a
**new, empty folder**, then copy just these four items from your old folder into it:

- `jobhunt.db` — your saved jobs, statuses, notes, and sent-application log
- `jobhunt_config.json` — your area, keyword tuning, and any API keys
- `jobhunt_secrets.json` — your email login
- the `resumes/` folder — the resume(s) you uploaded

Start it as usual — the first launch redoes the ~1-minute setup, and you're on the new
version with all your data intact. Once you've confirmed it works, you can delete the
old folder.

---

## Privacy

Everything runs and stays on your machine. These are **git-ignored and never
committed** (see `.gitignore`): your saved jobs (`jobhunt.db`), your live config
(`jobhunt_config.json`), your email login (`jobhunt_secrets.json`), and your uploaded
resume (`resumes/`). The repo ships a blank `jobhunt_config.example.json` for
reference; the app creates your real config on first run.

**Be respectful:** run from a home connection (not a cloud server or VPN), fetch only
a few times a day, review every application before sending, and keep it to personal
use.

---

## For developers

Pure Python standard library plus two packages (`requests`, `feedparser` — see
`requirements.txt`); the front end is vanilla HTML/CSS/JS with
[Leaflet](https://leafletjs.com/) for the map.

```bash
pip install -r requirements.txt     # or use the launcher, which makes a venv for you
python jobhunt.py serve             # web app at http://127.0.0.1:8765
python jobhunt.py serve --host 0.0.0.0   # also reachable from the LAN (no auth — home networks only)
# CLI also available:
python jobhunt.py fetch             # pull sources
python jobhunt.py list              # browse, ranked by fit
python jobhunt.py mark <id> interested
python jobhunt.py report            # static HTML report
```

**How in-app updates work:** the open page re-checks every 5 minutes (server-side
GitHub cache: 4 minutes), so a push shows up in a running app within ~10 minutes
with no refresh. The start files run `_boot.py`, a small stdlib-only
supervisor that installs `requirements.txt` when it changes, restarts the server
when it exits with code 42 (the "I just updated myself" signal), and — right
after an update — health-checks the new server, restoring `.backup/` and
relaunching the old version if it won't boot. `update_util.py` does the check
(GitHub commits API, compared against `version.json`) and the swap (the repo
zipball, extracting **only** paths whitelisted in `update_manifest.json`; the
db, config, secrets, resumes, and exclude list can never be written). Inside a
git checkout the updater disables itself — update with `git pull`. Note that
**pushing to `main` is publishing**: every install offers it as an update within
a day, so keep experiments on branches.

The cover note and follow-up email templates live in `jobhunt_config.json` under
`outreach` (`cover_template`, `followup_template`) and are editable in **⚙ Settings**
(cover note) or the config file directly.

`docs/` is a self-contained, no-backend build (baked sample data) that powers the live
demo via GitHub Pages, and can be hosted on any static site to show the app off.
