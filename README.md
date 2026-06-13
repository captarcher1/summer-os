# Summer.GG

An AI-powered summer growth planner built for a teenager. It balances sports, gaming, financial literacy, Taekwondo, reading, family time, and chores through a gamified XP engine, local AI scheduling, and a parent oversight dashboard — all running on your home network with no cloud accounts or subscriptions.

---

## What it does

- Generates personalised daily schedules using a local LLM (Ollama) that adapts based on recent XP, balance flags, and streaks
- Awards XP for completing activities; converts XP into earned gaming hours (500 XP = ~1.5 hrs, configurable)
- Tracks streaks, levels, and milestone rewards with confetti animations on every win
- Detects category imbalances (gaming overruns, missed movement days) and rebalances the next plan
- Teaches financial literacy through a 3-tier lesson track with AI-generated content and quiz gates
- Paper trading with live market data via yfinance — live ticker quotes as you type, AI coach reviews your investment thesis before any trade executes, yes/no confirmation gates final execution
- Daily quote cycling in the startup banner — pool grows every time Ollama generates a new one
- Gives parents a PIN-gated dashboard with compliance metrics, earnings tracker (XP → $), selective reset, and AI week reviews
- "How to Use" guide tab built in — kid-facing with collapsible parent section

---

## Stack

| Layer | Technology |
|-------|------------|
| Web server | Python / Flask |
| AI engine | Ollama (local LLM — qwen3:8b or qwen3.5:9b) |
| Database | SQLite (11 tables) |
| Market data | yfinance (free, no API key needed) |
| Frontend | Jinja2 templates + vanilla JS, no build step |

Runs entirely on your home network. No cloud, no subscription, no data leaving your machine.

---

## Project structure

```
summer-os/
├── app.py                   Entry point — run this
├── config.py                All tunables (XP rates, gaming tiers, Ollama URL)
├── requirements.txt
├── start_summer_os.bat      Windows: auto-start script (idempotent — safe to run anytime)
├── stop_summer_os.bat       Windows: graceful shutdown script (Flask only, Ollama untouched)
├── .env.example             Copy to .env and fill in your values
├── database/
│   ├── models.py            SQLite schema (11 tables) + query helpers + migrations
│   └── seed.py              Default activities, lessons, settings
├── services/
│   ├── ai_engine.py         Ollama client — schedule, coach notes, lessons, quotes, trade feedback
│   ├── xp_engine.py         XP ledger, levels, streaks, gaming unlocks
│   ├── scheduler.py         Daily schedule generator (AI + fallback templates)
│   ├── balance_detector.py  Category imbalance and gaming overrun detection
│   └── market_data.py       Paper portfolio and trade execution via yfinance
├── routes/
│   ├── dashboard.py         Today view, daily quote API, shared endpoints
│   ├── xp.py                XP logging, streak freeze, bonus XP
│   ├── schedule.py          Schedule generation and retrieval
│   ├── finance.py           Portfolio, trades, lessons, quiz, AI explanations
│   └── parent.py            PIN auth, settings, earnings tracker, lesson generation, reset
├── templates/
│   ├── base.html            Nav + shared layout (6 tabs including Guide)
│   ├── dashboard.html       Today — core loop card, schedule, XP progress, coach note
│   ├── week.html            Weekly grid — colour-coded schedule + balance bars
│   ├── finance.html         Expandable tier lessons, paper trading, portfolio P&L
│   ├── rewards.html         XP rates, gaming tiers, streak calendar, milestones
│   ├── parent.html          PIN gate, expandable sections, earnings tracker, reset
│   └── howto.html           Kid-first guide with collapsible parent section
└── static/
    ├── css/app.css
    └── js/app.js            Shared JS: theme, weather, nav XP, confetti, logActivity
```

---

## Prerequisites

### Windows

- **Python 3.10+** — download from [python.org](https://www.python.org/downloads/). During install, tick **"Add Python to PATH"**.
- **pip** — included with Python. Verify: `pip --version` in PowerShell.
- **Git** (optional) — to clone this repo. Download from [git-scm.com](https://git-scm.com).
- **Firewall** — Windows Firewall will prompt when you first run the app. Click **"Allow access"** so devices on your local network can reach it.

### macOS

- **Python 3.10+** — install via [Homebrew](https://brew.sh): `brew install python` or download from python.org.
- Use `python3` and `pip3` instead of `python` and `pip` in the commands below.
- No firewall configuration needed for LAN access by default.

### Linux (Ubuntu / Debian)

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv -y
```

Use `python3` and `pip3` in place of `python` and `pip`.

---

## Install Ollama and pull the model

### 1. Install Ollama

| OS | Steps |
|----|-------|
| **Windows** | Download and run the installer from [ollama.com/download](https://ollama.com/download). Ollama installs as a background service. |
| **macOS** | Download the `.dmg` from [ollama.com/download](https://ollama.com/download), drag to Applications, then open it. |
| **Linux** | `curl -fsSL https://ollama.com/install.sh \| sh` |

### 2. Pull the model

Open a terminal and run:

```bash
ollama pull qwen3:8b
```

This downloads ~5 GB. The 8B model needs about **8 GB of RAM** to run comfortably. If your machine has less than 8 GB, try the smaller variant:

```bash
ollama pull qwen3:4b
```

Then update `OLLAMA_MODEL` in your `.env` to match (e.g. `qwen3:4b`).

### 3. Verify the model is ready

```bash
ollama list
```

You should see `qwen3:8b` (or your chosen model) in the output.

### 4. Keep Ollama running

```bash
ollama serve
```

The app will try to start Ollama automatically on boot, but running it manually first avoids the 30-second cold-start wait.

---

## Setup

### 1. Clone or download the project

```bash
git clone <repo-url> summer-os
cd summer-os
```

Or download and unzip into a folder called `summer-os`.

### 2. Create a virtual environment (recommended)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
STUDENT_NAME=YourKidsName
STUDENT_AGE=15
PARENT_PIN=your_pin_here      # change from default 1234
SECRET_KEY=any-random-string
OLLAMA_MODEL=qwen3:8b         # match whatever you pulled above
```

---

## Running the app

### On the parent's machine

```bash
# Windows (with venv active)
python app.py

# macOS / Linux
python3 app.py
```

The app starts on `http://0.0.0.0:5000` and prints a local URL. First boot takes 30–60 seconds as the AI model loads into memory.

### Option A — Same WiFi (local network access)

This is the simplest setup. Both devices must be on the same home WiFi.

**Step 1: Find your PC's local IP**
- Open PowerShell and run `ipconfig`
- Look for **IPv4 Address** under your WiFi adapter — e.g. `192.168.1.100`

**Step 2 (recommended): Set a static IP so it never changes**

By default your router assigns your PC a new IP on every restart. To lock it in:

1. Open **Settings → Network & Internet → WiFi → Hardware properties**
2. Click **Edit** next to IP assignment
3. Switch from **Automatic (DHCP)** to **Manual**
4. Toggle **IPv4** on and fill in:
   - **IP address:** your current IP (e.g. `192.168.1.100`)
   - **Subnet mask:** `255.255.255.0`
   - **Gateway:** your router IP (usually `192.168.1.1`)
   - **DNS:** `8.8.8.8`
5. Click **Save**

Your PC will now always be reachable at that address on your home network.

**Step 3: Allow the app through Windows Firewall**

Run this once in PowerShell as Administrator:
```powershell
New-NetFirewallRule -DisplayName "Summer-OS Flask" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

**Step 4: Access from the child's device**

On any device connected to the same WiFi, open a browser and go to:
```
http://192.168.1.100:5000
```
(replace with your actual static IP)

Bookmark it. No app install needed — it's a web app.

---

### Option B — Tailscale VPN (access from anywhere)

Use this if the kid needs to access the app from outside your home WiFi — on mobile data, at a friend's house, or on another network. Tailscale creates a private encrypted tunnel between devices. No port-forwarding, no public internet exposure.

**On the parent's PC (server)**

1. Go to [tailscale.com](https://tailscale.com) and create a free account (supports up to 100 devices)
2. Download and install the **Windows** client from [tailscale.com/download](https://tailscale.com/download)
3. Click the Tailscale icon in the system tray (bottom-right) → **Log in**
4. Sign in with your Tailscale account in the browser window that opens
5. Note your **Tailscale IP**: click the tray icon — it shows an IP starting with `100.` (e.g. `100.x.x.x`)
6. Allow the app through the firewall (if not already done):
   ```powershell
   New-NetFirewallRule -DisplayName "Summer-OS Flask" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
   ```

**On a Windows device**

1. Go to [tailscale.com/download](https://tailscale.com/download) and download the Windows installer
2. Run the installer
3. Click the Tailscale tray icon → **Log in** → sign in with the **same Tailscale account**
4. Tailscale is now active — the device gets its own `100.x.x.x` IP

**On an Android device**

1. Open **Google Play Store** → search for **Tailscale** (by Tailscale Inc.)
2. Install and open the app
3. Tap **Log in** → sign in with the **same Tailscale account**
4. Toggle Tailscale **on** — tap **OK** when prompted to allow VPN access

**On an iPhone or iPad**

1. Open the **App Store** → search for **Tailscale** (by Tailscale Inc.)
2. Install and open the app
3. Tap **Log in** → sign in with the **same Tailscale account**
4. Toggle Tailscale **on** — tap **Allow** when prompted to add a VPN configuration

**Accessing the app**

From any device with Tailscale running, open a browser and go to:
```
http://100.x.x.x:5000
```
(replace with your PC's actual Tailscale IP from Step 5 above)

This works on home WiFi, mobile data, or any other network — as long as:
- Tailscale is running on both devices
- `python app.py` is running on the parent's PC

Bookmark the Tailscale URL on each device.

---

## First-run checklist

After starting the app for the first time:

1. Open the **Parent** tab (`/parent-page`) and enter the default PIN `1234`
2. Go to **Override Controls** → set the student's name, age, and gender (used to personalise AI prompts)
3. Change the parent PIN immediately
4. Go to **Generate AI Finance Lessons** → click **"Generate (up to 5)"** for each tier to add lesson topics
5. Then click **"Pre-generate all lesson content"** — this caches lesson text and quiz questions so the Finance tab opens instantly. Takes a few minutes but only needs to be done once (re-run after adding new lessons)
6. Set the **XP → dollar rate** in Override Controls to whatever conversion you want to use as a real incentive

---

## Parent controls

Open `/parent-page` and enter your PIN. All sections are expandable — click any header to expand or collapse:

| Section | What it does |
|---------|--------------|
| Real earnings tracker | Shows total XP converted to dollars at your configured rate |
| Generate AI finance lessons | Add new lesson titles (Step 1) + pre-generate content (Step 2) |
| AI flag alerts | Weekly balance flags — gaming overruns, missed movement, etc. |
| Activity breakdown | Category-by-category XP breakdown for the week |
| Override controls | Gaming cap, weekend XP minimum, student profile, XP→$ rate |
| Manual XP award | Award or deduct XP with a reason (e.g. "helped a neighbour") |
| XP rates per activity | Adjust how much each activity is worth |
| Change parent PIN | Self-explanatory |
| Initialize / reset app | Selective reset — choose exactly which data to wipe by checkbox |

---

## Finance module

Three tiers, each collapsible in the Finance tab:

| Tier   | Lessons | Topics | Unlocks when |
|--------|---------|--------|--------------|
| Tier 1 | 10+ | Budgeting, compound interest, savings, inflation, credit | Available from day 1 |
| Tier 2 | 10+ | Stocks, P/E ratio, chart reading, position sizing, stop-loss | After Tier 1 complete |
| Tier 3 | 5+ | Screeners, technical signals, options intro | After Tier 2 complete |

**How lessons work:** Click a lesson to expand it → AI generates a 3–4 sentence explanation + 3 multiple-choice questions → answer all 3 correctly → claim XP. Sequential unlock: each lesson gates the next. After 2 failed attempts the correct answers are revealed and XP can still be claimed.

**Paper trading flow:**
1. Type a ticker — live price and day change % appear instantly below the input. Invalid tickers show a red error.
2. Enter shares, action (buy/sell), and a mandatory investment thesis.
3. Click **Review with AI Coach** — the AI analyses your thesis and returns a detailed review.
4. A yes/no prompt appears: confirm to execute, or cancel. The trade only goes through on explicit confirmation.

---

## Customising XP rates and gaming tiers

Edit `config.py` — changes take effect on next restart:

```python
XP_RATES = {
    "taekwondo":     100,
    "chores":        500,   # highest-value — intentional
    "finance_lesson": 150,
    ...
}

GAMING_TIERS = [
    (0,    0.0),   # 0 XP = no gaming
    (500,  1.5),   # 500 XP earned = 1.5 hrs unlocked
    (800,  2.5),
    (1000, 4.0),
]
```

XP rates can also be adjusted live from the Parent tab without restarting.

---

## Automation (Windows — auto start / stop)

Two batch scripts handle scheduled start and shutdown. Both are relative-path safe — no hardcoded user directories.

| Script | Purpose |
|--------|---------|
| `start_summer_os.bat` | Starts the Flask app if not already running. Idempotent — safe to fire multiple times. |
| `stop_summer_os.bat` | Kills the Flask process on port 5000. Leaves Ollama running. Safe if app is already stopped. |

Logs are written to `logs\summer_os_start.log` and `logs\summer_os_stop.log` (folder auto-created).

### Wiring up Task Scheduler

Open **PowerShell as Administrator** and run the commands below. They create a single task (`Summer-OS`) with four triggers: start at 6 AM daily, at logon, at startup, and stop at 11 PM daily.

> Replace `C:\path\to\summer-os` with your actual project folder path in each command.

**1 — Auto-start at 6:00 AM every day**
```powershell
schtasks /Create /TN "Summer-OS\Start 6AM" /TR "\"C:\path\to\summer-os\start_summer_os.bat\"" /SC DAILY /ST 06:00 /RU SYSTEM /F
```

**2 — Auto-start at system logon**
```powershell
schtasks /Create /TN "Summer-OS\Start At Logon" /TR "\"C:\path\to\summer-os\start_summer_os.bat\"" /SC ONLOGON /RU SYSTEM /F
```

**3 — Auto-start at system startup**
```powershell
schtasks /Create /TN "Summer-OS\Start At Startup" /TR "\"C:\path\to\summer-os\start_summer_os.bat\"" /SC ONSTART /RU SYSTEM /F
```

**4 — Auto-stop at 11:00 PM every day**
```powershell
schtasks /Create /TN "Summer-OS\Stop 11PM" /TR "\"C:\path\to\summer-os\stop_summer_os.bat\"" /SC DAILY /ST 23:00 /RU SYSTEM /F
```

To verify all four tasks were created:
```powershell
schtasks /Query /TN "Summer-OS" /FO LIST
```

To remove all Summer-OS tasks if needed:
```powershell
schtasks /Delete /TN "Summer-OS" /F
```

### How the idempotent start works

The start script checks whether port 5000 is already bound before doing anything. This means all three start triggers (6 AM, logon, startup) can safely overlap — only the first one to run actually starts the app; the others log "already running" and exit silently.

---

## Summer dates

Set `SUMMER_START` and `SUMMER_END` in your `.env`. Default is June 1 – August 31.

```
SUMMER_START=2025-06-01
SUMMER_END=2025-08-31
```
