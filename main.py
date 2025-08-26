from keep_alive import keep_alive

keep_alive()

import time
import os
import requests
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

print("🟢 Script started...")

# adhanpy imports
from adhanpy.PrayerTimes import PrayerTimes
from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.calculation.CalculationParameters import CalculationParameters
from adhanpy.calculation.Madhab import Madhab
from adhanpy.calculation.HighLatitudeRule import HighLatitudeRule

# Only these prayers get an "ended" notification
END_NOTIFY = {"fajr", "maghrib"}

# =========================
# Config / Environment
# =========================
LATITUDE = float(os.environ["LATITUDE"])
LONGITUDE = float(os.environ["LONGITUDE"])
TIMEZONE = ZoneInfo(os.environ["TIMEZONE"])  # e.g., Europe/London

# London reference (East London Mosque area) used by LUPT distribution
REF_LAT = 51.5162
REF_LON = -0.0650

# Optional: if missing/invalid, script falls back to MWL automatically
LUPT_API_KEY = os.environ.get("LUPT_API_KEY")

# Debug logging
DEBUG = True
def _dbg(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# ===============
# Telegram helper
# ===============
def send_telegram_message(message, html=False):
    bot_token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML" if html else None
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


# ======================
# Summary message helper
# ======================
def send_daily_prayer_summary(prayer_start, prayer_end, today, method_label=""):
    """
    Sends a neatly aligned prayer-time table (non-jamaat start times).
    """
    COL = 24
    def row(emoji, label, tm):
        line = f"{emoji} {label}:"
        return f"{line.ljust(COL)}{tm.strftime('%H:%M')}"

    header = f"📍 Prayer Times for {today.strftime('%a %d-%m-%y')} (Rainham, LDN 🇬🇧)"
    msg_lines = [
        header,
        "",
        row("🌅", "Fajr starts", prayer_start['fajr']),
        row("   ⏳", "Ends", prayer_end['fajr']),
        "",
        row("🕛", "Dhuhr starts", prayer_start['dhuhr']),
        row("   ⏳", "Ends", prayer_end['dhuhr']),
        "",
        row("🕒", "Asr starts", prayer_start['asr']),
        row("   ⏳", "Ends", prayer_end['asr']),
        "",
        row("🌇", "Maghrib starts", prayer_start['maghrib']),
        row("   ⏳", "Ends", prayer_end['maghrib']),
        "",
        row("🌃", "Isha starts", prayer_start['isha']),
        row("   ⏳", "Ends", prayer_end['isha']),
        "",
        row("🌌", "Tahajjud starts", prayer_start['tahajjud']),
        row("   ⏳", "Ends", prayer_end['tahajjud']),
    ]
    message = "<pre>\n" + "\n".join(msg_lines) + "\n</pre>"
    send_telegram_message(message, html=True)


# ======================
# LUPT fetch + utilities
# ======================
def _hhmm_to_dt_local(hhmm: str, day: date) -> datetime:
    # LUPT returns "HH:MM" in local UK time; construct localized datetime
    H, M = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, H, M, tzinfo=TIMEZONE)

def _shift_dt(dt: datetime, minutes: int) -> datetime:
    return dt + timedelta(minutes=minutes)

def _get_solar_events(day: date, lat: float, lon: float, tz: ZoneInfo):
    """
    Use adhanpy to get sunrise, solar noon (dhuhr), sunset at a location.
    Angles/method don't affect these solar events.
    """
    params = CalculationParameters(
        fajr_angle=18, isha_angle=17, method=CalculationMethod.MUSLIM_WORLD_LEAGUE
    )
    params.madhab = Madhab.HANAFI
    params.high_latitude_rule = HighLatitudeRule.TWILIGHT_ANGLE

    pt = PrayerTimes((lat, lon), day, calculation_parameters=params, time_zone=tz)
    return {
        "sunrise": pt.sunrise,
        "solar_noon": pt.dhuhr,   # solar transit
        "sunset": pt.maghrib      # start of maghrib
    }

def _get_asr_hanafi(day: date, lat: float, lon: float, tz: ZoneInfo) -> datetime:
    """
    True Hanafi (Mithl-2) Asr at given coords using adhanpy (shadow-length based, not angle-based).
    """
    params = CalculationParameters(
        fajr_angle=18, isha_angle=17, method=CalculationMethod.MUSLIM_WORLD_LEAGUE
    )
    params.madhab = Madhab.HANAFI
    params.high_latitude_rule = HighLatitudeRule.TWILIGHT_ANGLE
    pt = PrayerTimes((lat, lon), day, calculation_parameters=params, time_zone=tz)
    return pt.asr

def _fetch_lupt_times(day: date):
    """
    Returns official London (non-jamaat) times (datetime in TIMEZONE) or None if not available.
    Flexible parser: supports flat JSON (today) and legacy {"times":[...]}.
    Fields normalized: fajr, sunrise, dhuhr, asr, maghrib, isha
    """
    if not LUPT_API_KEY:
        _dbg("No LUPT_API_KEY set; will use MWL fallback.")
        return None

    url = "https://www.londonprayertimes.com/api/times/"
    params = {
        "format": "json",
        "key": LUPT_API_KEY,
        "date": day.strftime("%Y-%m-%d"),
        "city": "london",
        "24hours": "true",   # ensure HH:MM
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        _dbg(f"LUPT GET {r.url} -> HTTP {r.status_code}")
        if r.status_code != 200:
            _dbg(f"LUPT non-200 body: {r.text[:200]}")
            return None

        data = r.json()

        # Determine row shape
        row = None
        if isinstance(data, dict) and any(k in data for k in ("fajr","sunrise","dhuhr","asr","isha","magrib","maghrib")):
            row = data
        elif isinstance(data, dict) and isinstance(data.get("times"), list) and data["times"]:
            row = data["times"][0]
        else:
            _dbg("LUPT unknown JSON shape; keys: " + ", ".join(list(data.keys())[:10]))
            return None

        maghrib_key = "maghrib" if "maghrib" in row else "magrib"

        _dbg(f"LUPT row: fajr={row.get('fajr')} sunrise={row.get('sunrise')} dhuhr={row.get('dhuhr')} "
             f"asr={row.get('asr')} {maghrib_key}={row.get(maghrib_key)} isha={row.get('isha')}")

        return {
            "fajr": _hhmm_to_dt_local(row["fajr"], day),
            "sunrise": _hhmm_to_dt_local(row["sunrise"], day),
            "dhuhr": _hhmm_to_dt_local(row["dhuhr"], day),
            "asr": _hhmm_to_dt_local(row["asr"], day),  # often Mithl-1 in API; we'll recompute Hanafi below
            "maghrib": _hhmm_to_dt_local(row[maghrib_key], day),
            "isha": _hhmm_to_dt_local(row["isha"], day),
        }
    except Exception as e:
        _dbg(f"LUPT fetch error: {e}")
        return None


# ==============================================
# 🕰️ Prayer Calculation (LUPT coord-adjusted)
# ==============================================
def calculate_prayer_times():
    today = datetime.now(TIMEZONE).date()

    lupt = _fetch_lupt_times(today)

    if lupt:
        # Compute solar deltas between your coords and the LUPT reference
        ref = _get_solar_events(today, REF_LAT, REF_LON, TIMEZONE)
        you = _get_solar_events(today, LATITUDE, LONGITUDE, TIMEZONE)

        d_sunrise = round((you["sunrise"] - ref["sunrise"]).total_seconds() / 60)
        d_noon    = round((you["solar_noon"] - ref["solar_noon"]).total_seconds() / 60)
        d_sunset  = round((you["sunset"] - ref["sunset"]).total_seconds() / 60)
        _dbg(f"Deltas (mins): sunrise={d_sunrise}, noon={d_noon}, sunset={d_sunset}")

        # Shift official LUPT times by deltas (non-jamaat starts)
        fajr    = _shift_dt(lupt["fajr"], d_sunrise)     # HU-based start
        sunrise = _shift_dt(lupt["sunrise"], d_sunrise)
        dhuhr   = _shift_dt(lupt["dhuhr"], d_noon)       # solar transit + 5min already in LUPT
        # ✅ Recompute Asr at your coords using Hanafi (Mithl-2), not the API's single asr field
        asr     = _get_asr_hanafi(today, LATITUDE, LONGITUDE, TIMEZONE)
        maghrib = _shift_dt(lupt["maghrib"], d_sunset)   # sunset + 3min already in LUPT
        isha    = _shift_dt(lupt["isha"], d_sunset)      # HU-based start

        _dbg(f"API Asr (likely Mithl-1): {lupt['asr'].strftime('%H:%M')} | Hanafi Asr at coords: {asr.strftime('%H:%M')}")

        # Night window for Tahajjud (maghrib -> next fajr)
        night_start = maghrib
        night_end = fajr if fajr > night_start else (fajr + timedelta(days=1))
        night_duration = night_end - night_start
        tahajjud = night_start + (night_duration * 2 / 3)
        tahajjud = (tahajjud + timedelta(seconds=(60 - tahajjud.second) % 60)).replace(second=0, microsecond=0)

        maghrib_end = maghrib + timedelta(minutes=30)

        prayer_start = {
            "fajr": fajr,
            "dhuhr": dhuhr,
            "asr": asr,
            "maghrib": maghrib,
            "isha": isha,
            "tahajjud": tahajjud
        }
        prayer_end = {
            "fajr": sunrise,
            "dhuhr": asr,
            "asr": maghrib,
            "maghrib": maghrib_end,
            "isha": night_end,   # ends at next fajr
            "tahajjud": night_end
        }
        method_label = "LUPT (official, non-jamāʿat) · Hanafi/Mithl-2 · coord-adjusted"
    else:
        _dbg("Using MWL fallback (no LUPT times).")
        location = (LATITUDE, LONGITUDE)
        params = CalculationParameters(
            fajr_angle=18,
            isha_angle=17,
            method=CalculationMethod.MUSLIM_WORLD_LEAGUE
        )
        params.madhab = Madhab.HANAFI
        params.high_latitude_rule = HighLatitudeRule.TWILIGHT_ANGLE

        pt = PrayerTimes(location, today, calculation_parameters=params, time_zone=TIMEZONE)

        maghrib = pt.maghrib
        maghrib_end = maghrib + timedelta(minutes=30)
        isha_astro = pt.isha
        isha_cap = maghrib + timedelta(minutes=80)
        isha = isha_cap if isha_astro.hour >= 23 else isha_astro

        night_start = maghrib
        night_end = pt.fajr + timedelta(days=1)
        night_duration = night_end - night_start
        tahajjud = night_start + (night_duration * 2 / 3)
        if tahajjud.second > 0:
            tahajjud += timedelta(minutes=1)
        tahajjud = tahajjud.replace(second=0, microsecond=0)

        prayer_start = {
            "fajr": pt.fajr,
            "dhuhr": pt.dhuhr,
            "asr": pt.asr,            # Hanafi from library params
            "maghrib": maghrib,
            "isha": isha,
            "tahajjud": tahajjud
        }
        prayer_end = {
            "fajr": pt.sunrise,
            "dhuhr": pt.asr,
            "asr": maghrib,
            "maghrib": maghrib_end,
            "isha": pt.fajr,
            "tahajjud": pt.fajr
        }
        method_label = "MWL fallback (non-jamāʿat) · Hanafi"

    # 20-min-before-end reminders
    prayer_reminder = {
        name: (end_time - timedelta(minutes=20)).replace(second=0, microsecond=0)
        for name, end_time in prayer_end.items()
    }
    return prayer_start, prayer_end, prayer_reminder, method_label


# 🔁 Loop
def run_reminder_loop():
    current_day = datetime.now(TIMEZONE).date()
    prayer_start, prayer_end, prayer_reminder, method_label = calculate_prayer_times()
    send_daily_prayer_summary(prayer_start, prayer_end, current_day, method_label)

    while True:
        now = datetime.now(TIMEZONE).replace(second=0, microsecond=0)
        now_str = now.strftime('%H:%M')

        # ⏰ Daily reset + summary at 00:01
        if datetime.now(TIMEZONE).date() != current_day or now_str == "00:01":
            current_day = datetime.now(TIMEZONE).date()
            prayer_start, prayer_end, prayer_reminder, method_label = calculate_prayer_times()
            send_daily_prayer_summary(prayer_start, prayer_end, current_day, method_label)

        # 1) ⏳ 20-min before end reminders (unchanged; for all prayers)
        for name, reminder_time in prayer_reminder.items():
            if now_str == reminder_time.strftime('%H:%M'):
                msg = f"🔔 Reminder: {name.title()} ends soon at {prayer_end[name].strftime('%H:%M')}"
                print(msg)
                send_telegram_message(msg)

        # 2) 🚨 Ended notifications — ONLY for Fajr & Maghrib — and sent BEFORE starts
        for name, end_time in prayer_end.items():
            if name in END_NOTIFY and now_str == end_time.strftime('%H:%M'):
                msg = f"🚨 {name.title()} has ended: {end_time.strftime('%H:%M')}"
                print(msg)
                send_telegram_message(msg)

        # 3) ⏰ Start notifications (sent AFTER end notifications)
        for name, start_time in prayer_start.items():
            if now_str == start_time.strftime('%H:%M'):
                msg = f"⏰ {name.title()} has started: {start_time.strftime('%H:%M')}"
                print(msg)
                send_telegram_message(msg)

        time.sleep(60)

# ▶️ Run
if __name__ == "__main__":
    run_reminder_loop()