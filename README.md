# jobhunt

A small, **private** job-search helper that runs entirely on your own computer —
no accounts, no sign-ups, nothing uploaded anywhere. It pulls local job listings,
scores them by how well they fit you, shows them on a map with nearby transit,
and lets you apply and follow up without leaving the app.

**▶ Live demo (click around, no install): <https://davidfic.github.io/job-search/>**

> **Already using jobhunt?** It updates itself — when a new version is ready, a
> green **⬆ Update** button appears in the app. One click, and your saved jobs,
> settings, and resume are never touched. Details in
> **[🔄 Updating to a new version](#-updating-to-a-new-version)**.

It ships set up for a real example: finding a summer job around **Davis Square,
Somerville MA**. Different area? See [EXTRAS.md](EXTRAS.md#change-the-area).

---

## ▶️ Launch it

You only do **two things**: install Python once, then double-click a start file.

**Step 1 — Install Python (one time).**
Go to **<https://www.python.org/downloads/>**, click the big **Download Python**
button, and run the installer. **Windows users:** on the **first** installer screen,
check **“Add Python to PATH”** before clicking *Install Now* — this is the #1 thing
people miss.

**Step 2 — Get the files.**
On the [repo page](../../), click the green **Code** button → **Download ZIP**,
and unzip it. *(Or `git clone` this repo.)* You only do this once — after that,
jobhunt updates itself from inside the app.

**Step 3 — Start it.** Open the folder and double-click the start file for your
computer:

| Your computer | Double-click |
|---|---|
| **Windows** | `Start jobhunt (Windows).bat` |
| **Mac** | `Start jobhunt (Mac).command` |
| **Linux** | `start-jobhunt (Linux).sh` |

A small window opens; the **first** start takes about a minute, then your browser
opens the app automatically. If it doesn't, go to **<http://127.0.0.1:8765>**.
**To stop:** close the little window.

> **Windows:** the first start may ask to allow a firewall change — click **Yes**.
> (One time only; it lets you open the app from your phone too — see
> [EXTRAS.md](EXTRAS.md#use-it-from-your-phone-windows).)
>
> **Mac:** if you get *“cannot be opened because it is from an unidentified
> developer,”* right-click the start file → **Open** → **Open**. One time only.

---

## 🧭 Use it

1. Click **Fetch new jobs** (top right). When it finishes you land on the
   **🆕 Just fetched** tab, showing only what that fetch brought in.
2. Work through the cards — **★ Interested** or **✕ Not interested**. The tabs
   across the top keep everything sorted; the map shows each job with the nearby
   train and bus lines.
3. Every card has a **fit score** (higher = better match) and shows 💰 **pay**
   when the listing gives it.
4. Make the scores yours: the **Keywords** boxes in the sidebar boost terms you
   want and penalize ones you don't, and the **Exclude** box hides matching jobs
   instantly. Upload your **resume** in the sidebar — it suggests good keywords
   and gets attached when you apply.

---

## ✉️ Apply from the app

**One-time setup (2 minutes):**

1. Upload your **resume** in the sidebar.
2. Click **⚙ Settings** and fill in your **name, email, and phone** — they fill in
   your cover note automatically.
3. *(Recommended)* In the same Settings, set up **email sending** so applications
   go out directly with your resume attached. For Gmail: host `smtp.gmail.com`,
   port `587`, and an **App Password** — search "Gmail app password" to make one;
   your normal password won't work. Click **Send test connection** to check it.

**To apply to a job:**

1. Click **Apply** on the job's card.
2. If it says how-to-apply isn't known yet, click **🔎 Scan listing for contact
   info** — the app reads that one listing and finds the email, phone, or
   application link.
3. What you see next depends on the listing:

   | The app shows | What to do |
   |---|---|
   | **✉ email** — an address was found | Check the prefilled cover note, click **Send with resume**. Done. |
   | **CL reply** — a Craigslist listing | Craigslist hides the poster's email, so the app walks you through it: open the listing → click **reply** → copy the `…@reply.craigslist.org` address → paste it into **To** → **Send with resume**. Craigslist forwards it to the poster. |
   | **form** — an application website | Click **Open application page** and apply on their site. |

4. No email sending set up? Click **Open email draft** instead — it opens your own
   mail app prefilled (attach your resume there yourself).

Every application is marked **applied** and logged under **📤 Sent**, so you always
know who you contacted and when.

**Follow up — it works:** if a job you applied to has been quiet for **5 days**,
its card shows *“no reply yet? **Send a follow-up**.”* One click opens a short,
polite, prefilled check-in email. A follow-up meaningfully raises your odds of a
reply — send them.

---

## 🔄 Updating to a new version

**jobhunt updates itself.** When a new version is ready, a green **⬆ Update**
button appears at the top of the app. Click it, read what's new, click
**Update now** — the app installs the new version, restarts, and the page
reloads on its own. That's it.

Your personal data — saved jobs (`jobhunt.db`), settings
(`jobhunt_config.json`), email login (`jobhunt_secrets.json`), your Exclude
list, and your `resumes/` folder — is **never touched by an update**. And if a
new version somehow fails to start, jobhunt automatically puts the previous
version back.

> **Updating from an older jobhunt (before in-app updates)?** The very first
> update asks you to close the jobhunt window and double-click your start file
> once more. Every update after that finishes on its own.

<details>
<summary><b>Manual update</b> (fallback — you shouldn't normally need this)</summary>

1. **Close jobhunt** (close the little window).
2. **Download** the repo zip from GitHub (green **Code** button → Download ZIP)
   and unzip it.
3. Copy the new files into your existing jobhunt folder, choosing **Replace**.
   Your data files aren't in the download, so they can't be overwritten.
4. Double-click your usual start file.
</details>

---

## 🛟 If something goes wrong

| Problem | Fix |
|---|---|
| *“Python is not installed”* | Do the install step above, then double-click the start file again. On Windows, make sure you checked **Add Python to PATH**. |
| **No jobs appear** after Fetch | Check your internet, and **turn off any VPN** — Craigslist blocks VPNs and office networks. A normal home connection works. |
| The window closes by itself | Re-open the start file. If it keeps happening, screenshot any red text and ask for help. |
| **Something broke right after an update** | jobhunt restores the previous version automatically. If the app won't open at all, use the **Manual update** steps above to lay down fresh files — your data is safe either way. |
| Mac won't open the start file | Right-click → **Open** (see the Mac tip above). |

---

**Privacy, in one line:** everything runs and stays on your machine, and your
personal files are never committed or uploaded. Be respectful — fetch a few times
a day from a home connection, and review every application before it goes out.

**Want more?** **[EXTRAS.md](EXTRAS.md)** covers how the scoring works, adding
more job sources (free API keys), changing the area, using the app from your
phone, the full privacy notes, and the developer/CLI docs.
