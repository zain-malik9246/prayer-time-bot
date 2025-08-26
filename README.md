<img src="logo.png" alt="Alt text" width="300">
---

A personal Telegram bot that calculates **daily prayer times** at my **exact coordinates**, using the **London Unified Prayer Timetable (LUPT)** as a base.  
It adjusts for my location (since I don’t have a local mosque timetable) and follows the **Ḥanafī (Mithl-2) method for ʿAṣr**.

---

## ✨ Features
- 📍 Exact-coordinate adjustments of LUPT (sunrise / noon / sunset deltas)
- 🕒 Correct **Ḥanafī Asr** (shadow = 2× object height)
- 🔔 Telegram reminders:
  - “Ends soon” (20 minutes before prayer ends)
  - “Prayer ended” (only for **Fajr** & **Maghrib**)
  - “Prayer started” (for all prayers)
- 🌌 Tahajjud start time (last third of the night)

---

## ⚙️ Environment Variables

| Variable       | Description |
|----------------|-------------|
| `LATITUDE`     | Decimal latitude of your location |
| `LONGITUDE`    | Decimal longitude of your location |
| `TIMEZONE`     | e.g. `Europe/London` |
| `BOT_TOKEN`    | Telegram bot token from BotFather |
| `CHAT_ID`      | Your Telegram chat ID |
| `LUPT_API_KEY` | API key from [londonprayertimes.com](https://www.londonprayertimes.com/) |

---

## 🚀 Running locally

```bash
# clone and enter the repo
git clone https://github.com/yourusername/prayerbot.git
cd prayerbot

# (optional) create a venv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# install deps
pip install -r requirements.txt

# run
python main.py
```

---

## 📡 Deployment

Deployed on **Railway.app**.  
Environment variables are set in the Railway dashboard.

---

## 📖 How it works (short version)

- **Fajr & Isha** → from LUPT (Hizbul-Ulama twilight, not raw angles)  
- **Dhuhr** → solar noon + 5 minutes  
- **Asr** → recalculated at my coords using Ḥanafī (Mithl-2) shadow rule  
- **Maghrib** → sunset + 3 minutes  
- All times nudged to my exact location by comparing **sunrise / noon / sunset** between East London (LUPT reference) and my coords.

---

## 🔒 Note

This is a **personal project** for my own prayer schedule.  
Not intended as a public service or replacement for your local mosque timetable.
