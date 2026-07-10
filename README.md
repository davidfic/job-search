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
- 🆕 **“Just fetched” tab** — see only what the latest fetch pulled in, so new
  listings never get lost in the pile
- 🚫 **Keyword tuning** — boost good matches, hide listings you don't want, live
- 📄 **Resume upload** that suggests good-fit keywords from your resume
- ✉️ **Apply** from the app — find contact info, attach your resume, send or draft
- 💾 everything is local: one SQLite file, one JSON config
- 📱 On **Windows**, also works from your **phone or other devices** on your home Wi-Fi

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

- Click **Fetch new jobs** (top right) to pull listings. When it finishes, the app
  jumps to the **Just fetched** tab so you see only what that fetch brought in.
- Browse the ranked cards and the map; use the **tabs** to mark jobs
  *Interested* / *Not interested*.
- Tune the **Keywords** boxes, upload your **resume**, and hit **Apply** on a job.

**To stop:** just close the little window. To use it again later, double-click the
same start file.

> **Mac tip:** the first time, if you get *“cannot be opened because it is from an
> unidentified developer,”* **right-click** (or Control-click) the start file →
> **Open** → **Open**. You only do this once.

### 📱 Use it from your phone (Windows)

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

## 🔄 Updating to a new version

New versions arrive as a fresh **`jobhunt.zip`**. The good news: **your personal data
is never inside the download**, so updating can't overwrite it. These stay put in your
folder no matter how you update:

| File / folder | What it holds |
|---|---|
| `jobhunt.db` | your saved jobs, statuses, notes, and sent-application log |
| `jobhunt_config.json` | your area, keyword tuning, and any API keys |
| `jobhunt_secrets.json` | your email login |
| `resumes/` | the resume(s) you uploaded |

### Easiest — copy the new files over the old ones (recommended)

1. **Close jobhunt** — close the little window if it's still open.
2. **Download** the new `jobhunt.zip` from the [Releases](../../releases) page and
   **unzip** it.
3. Open the new unzipped folder, **select everything** (`Ctrl-A`, or `Cmd-A` on Mac)
   and **copy**.
4. **Paste** it into your existing jobhunt folder. When it asks, choose
   **Replace the files in the destination**.
5. Double-click your usual start file.

Your saved jobs and settings are untouched (they aren't part of the download), and
because the one-time setup folder (`.venv`) is reused, it **starts in seconds** — no
first-time setup wait.

> **If you customized the Exclude list in the app:** those terms live in
> `exclude_keywords.txt`, and this method resets that file to the shipped defaults. To
> keep your own terms, make a copy of that file before you paste — or just re-add them
> in the app afterward.

### Alternative — start clean in a new folder

Want a totally fresh copy (say things feel broken)? Unzip the new `jobhunt.zip` into a
**new, empty folder**, then copy just these four items from your old folder into it:

- `jobhunt.db`
- `jobhunt_config.json`
- `jobhunt_secrets.json`
- the `resumes/` folder

Start it as usual — the first launch redoes the ~1-minute setup, and you're on the new
version with all your data intact. Once you've confirmed it works, you can delete the
old folder.

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
python jobhunt.py serve --host 0.0.0.0   # also reachable from the LAN (no auth — home networks only)
# CLI also available:
python jobhunt.py fetch             # pull sources
python jobhunt.py list              # browse, ranked by fit
python jobhunt.py mark <id> interested
python jobhunt.py report            # static HTML report
```

`docs/` is a self-contained, no-backend build (baked sample data) that powers the live
demo via GitHub Pages, and can be hosted on any static site to show the app off.
