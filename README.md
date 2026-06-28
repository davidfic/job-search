# jobhunt

A small, **private** job-search helper that runs entirely on your own computer —
no accounts, no sign-ups, nothing uploaded anywhere. It pulls local job listings,
scores them by how well they fit you, shows them on a map with the nearby train and
bus lines, lets you triage and apply, and keeps track of everything in one local file.

It ships configured for a real example: **finding a summer job around Davis Square,
Somerville MA**, reachable by the Red Line and the Green Line E branch. You can point
it at any area by editing the config (see [Change the area](#change-the-area)).

**▶ Live demo (click around, no install): <https://davidfic.github.io/job-search/>**

- 🔎 Pulls listings from **Craigslist** (and optionally Adzuna) and scores them by fit
- 🗺️ **Map** of every job with the **Red Line**, **Green Line E** (out of Ball Square),
  and key Davis-area **bus routes**
- ✅ **Triage** tabs — mark jobs *Interested* / *Not interested*, filter instantly
- 🚫 **Keyword tuning** — boost good matches, hide listings you don't want, live
- 📄 **Resume upload** that suggests good-fit keywords from your resume
- ✉️ **Apply** from the app — find contact info, attach your resume, send or draft
- 💾 everything is local: one SQLite file, one JSON config

---

## ▶️ How to run it (no coding needed)

You only do **two things**: install Python once, then double-click a start file.

### Step 1 — Install Python (one time)

Python is the free engine this runs on.

1. Go to **<https://www.python.org/downloads/>**
2. Click the big **Download Python** button and run the installer.
3. **Windows users:** on the **first** installer screen, check the box
   **“Add Python to PATH”** before clicking *Install Now*. (This is the #1 thing
   people miss.)

### Step 2 — Get the files

**Easiest:** download the latest **`jobhunt.zip`** from the
[**Releases**](../../releases) page, then unzip it.

*(Or, if you use git: `git clone` this repo.)*

### Step 3 — Start it

Open the unzipped folder and **double-click** the start file for your computer:

| Your computer | Double-click |
|---|---|
| **Windows** | `Start jobhunt (Windows).bat` |
| **Mac** | `Start jobhunt (Mac).command` |
| **Linux** | `start-jobhunt (Linux).sh` |

A small window opens and says it's setting up. The **first** time this takes about a
minute (it downloads two small components). After that it starts in a couple seconds,
and your **web browser opens automatically** to the app. If it doesn't, go to:

> **<http://127.0.0.1:8765>**

### Step 4 — Use it

- Click **Fetch new jobs** (top right) to pull listings.
- Browse the ranked cards and the map; use the **tabs** to mark jobs
  *Interested* / *Not interested*.
- Tune the **Keywords** boxes, upload your **resume**, and hit **Apply** on a job.

**To stop:** just close the little window. To use it again later, double-click the
same start file.

> **Mac tip:** the first time, if you get *“cannot be opened because it is from an
> unidentified developer,”* **right-click** (or Control-click) the start file →
> **Open** → **Open**. You only do this once.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *“Python is not installed”* | Do **Step 1**, then double-click the start file again. On Windows, make sure you checked **Add Python to PATH**. |
| **No jobs appear** after Fetch | Check your internet, and **turn off any VPN** — the job site (Craigslist) blocks VPNs and company networks. A normal home connection works. |
| The window closes by itself | Re-open the start file. If it keeps happening, screenshot any red text and ask for help. |
| Mac won't open the start file | Right-click → **Open** (see the Mac tip above). |

---

## What it does (in more detail)

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

### Sources

| Source | On by default | Key needed? |
|---|---|---|
| **Craigslist** (Boston) | ✅ yes | no |
| **Adzuna** (local distance filtering) | enabled, but idle until you add free keys | yes (free) |
| RemoteOK / Remotive / We Work Remotely | off (remote-tech jobs) | no |

### Applying from the app

Each job card has an **Apply** button: it scans that one listing for an email /
phone / application link, lets you attach your uploaded resume and edit a cover note,
and then **sends from your own email** (if you set that up in Settings) or opens a
prefilled draft / the application page. Everything is reviewed by you, one at a time,
and logged. See Settings for email setup (Gmail needs an **App Password**).

---

## Change the area

Everything about location lives in `jobhunt_config.json` under `location_filter`
(swap the `walkable` / `allow` / `block` neighborhood lists and the `home`), the
Craigslist `searches`, and `geo_data.py` (the map's coordinates and transit lines).

To add more local listings, get free keys at <https://developer.adzuna.com/> and
paste them into the `adzuna` section of `jobhunt_config.json`.

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

Pure Python standard library plus two packages (`requests`, `feedparser`); the
front end is vanilla HTML/CSS/JS with [Leaflet](https://leafletjs.com/) for the map.

```bash
pip install requests feedparser     # or use the launcher, which makes a venv for you
python jobhunt.py serve             # web app at http://127.0.0.1:8765
# CLI also available:
python jobhunt.py fetch             # pull sources
python jobhunt.py list              # browse, ranked by fit
python jobhunt.py mark <id> interested
python jobhunt.py report            # static HTML report
```

`docs/` is a self-contained, no-backend build (baked sample data) that powers the live
demo via GitHub Pages, and can be hosted on any static site to show the app off.
