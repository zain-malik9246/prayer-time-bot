from keep_alive import keep_alive

keep_alive()

import time
import os
import requests
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

print("🟢 Script started...")

from adhanpy.PrayerTimes import PrayerTimes
from adhanpy.calculation.CalculationMethod import CalculationMethod
from adhanpy.calculation.CalculationParameters import CalculationParameters
from adhanpy.calculation.Madhab import Madhab
from adhanpy.calculation.HighLatitudeRule import HighLatitudeRule

# =========================
# Constants / Configuration
# =========================
LATITUDE = float(os.environ["LATITUDE"])
LONGITUDE = float(os.environ["LONGITUDE"])
TIMEZONE = ZoneInfo(os.environ["TIMEZONE"])

# London reference point used by the official timetable (East London Mosque area)
REF_LAT = 51.5162
REF_LON = -0.0650

# Optional: if missing, script falls back to MWL automatically
LUPT_API_KEY = os.environ.get("LUPT_API_KEY")

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
def send_daily_prayer_summary(prayer_start, prayer_end, today):
    """
    Sends a neatly aligned prayer-time table.
    ── column width is fixed (24 chars) so the HH:MM values line up.
    """
    COL = 24

    def row(emoji, label, tm):
        line = f"{emoji} {label}:"
        return f"{line.ljust(COL)}{tm.strftime('%H:%M')}"

    msg_lines = [
        f"📍 Prayer Times for {today.strftime('%a %d-%m-%y')} (Rainham, LDN 🇬🇧)",
        "",
        row("🌅", "Fajr starts", prayer_start['fajr']),
        row("   ⏳", "Ends", prayer_end['fajr']),
        "",
        row("🕛", "Dhuhr starts", prayer_start['dhuhr']),
        row("   ⏳", "Ends", prayer_end['dhuhr']),
        "",
        row("🕒", "Asr (Hanafi) starts", prayer_start['asr']),
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
        "sunset": pt.maghrib      # raw sunset (start of maghrib)
    }

def _fetch_lupt_times(day: date):
    """
    Returns official London times (datetime in TIMEZONE) or None if not available.
    Fields: fajr, sunrise, dhuhr, asr_mithl1, asr_mithl2, maghrib, isha
    """
    if not LUPT_API_KEY:
        return None

    url = "https://www.londonprayertimes.com/api/times/"
    params = {
        "format": "json",
        "city": "london",
        "date": day.strftime("%Y-%m-%d"),
        "key": LUPT_API_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            print(f"LUPT HTTP {r.status_code} – falling back to MWL.")
            return None
        data = r.json()
        row = (data.get("times") or [None])[0]
        if not row:
            print("LUPT response empty – falling back to MWL.")
            return None

        return {
            "fajr": _hhmm_to_dt_local(row["fajr"], day),
            "sunrise": _hhmm_to_dt_local(row["sunrise"], day),
            "dhuhr": _hhmm_to_dt_local(row["dhuhr"], day),
            "asr_mithl1": _hhmm_to_dt_local(row.get("asr_mithl1", row.get("asr")), day),
            "asr_mithl2": _hhmm_to_dt_local(row.get("asr_mithl2", row.get("asr")), day),
            "maghrib": _hhmm_to_dt_local(row["maghrib"], day),
            "isha": _hhmm_to_dt_local(row["isha"], day),
        }
    except Exception as e:
        print(f"LUPT fetch error: {e} – falling back to MWL.")
        return None


# ==============================================
# 🕰️ Prayer Calculation (LUPT coord-adjusted)
# ==============================================
def calculate_prayer_times():
    today = datetime.now(TIMEZONE).date()

    # 1) Attempt official LUPT
    lupt = _fetch_lupt_times(today)

    if lupt:
        # 2) Compute solar deltas between your coords and the LUPT reference
        ref = _get_solar_events(today, REF_LAT, REF_LON, TIMEZONE)
        you = _get_solar_events(today, LATITUDE, LONGITUDE, TIMEZONE)

        # minute deltas
        d_sunrise = round((you["sunrise"] - ref["sunrise"]).total_seconds() / 60)
        d_noon    = round((you["solar_noon"] - ref["solar_noon"]).total_seconds() / 60)
        d_sunset  = round((you["sunset"] - ref["sunset"]).total_seconds() / 60)

        # 3) Shift official LUPT times by physical deltas (Hanafi Asr = Mithl 2)
        fajr    = _shift_dt(lupt["fajr"], d_sunrise)
        sunrise = _shift_dt(lupt["sunrise"], d_sunrise)
        dhuhr   = _shift_dt(lupt["dhuhr"], d_noon)
        asr     = _shift_dt(lupt["asr_mithl2"], d_noon)  # ✅ Hanafi (Mithl 2)
        maghrib = _shift_dt(lupt["maghrib"], d_sunset)
        isha    = _shift_dt(lupt["isha"], d_sunset)

        # Night window (for tahajjud) uses your coord-adjusted maghrib→fajr
        night_start = maghrib
        night_end = fajr if fajr > night_start else (fajr + timedelta(days=1))
        night_duration = night_end - night_start
        tahajjud = night_start + (night_duration * 2 / 3)
        tahajjud = (tahajjud + timedelta(seconds=(60 - tahajjud.second) % 60)).replace(second=0, microsecond=0)

        # Ends:
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
            "isha": night_end,        # Isha ends at next Fajr
            "tahajjud": night_end
        }
    else:
        # =========================
        # Fallback: original MWL (Hanafi)
        # =========================
        location = (LATITUDE, LONGITUDE)
        params = CalculationParameters(
            fajr_angle=18,
            isha_angle=17,
            method=CalculationMethod.MUSLIM_WORLD_LEAGUE
        )
        params.madhab = Madhab.HANAFI
        params.high_latitude_rule = HighLatitudeRule.TWILIGHT_ANGLE

        prayer_times = PrayerTimes(location, today, calculation_parameters=params, time_zone=TIMEZONE)

        maghrib = prayer_times.maghrib
        maghrib_end = maghrib + timedelta(minutes=30)
        isha_astro = prayer_times.isha
        isha_cap = maghrib + timedelta(minutes=80)
        isha = isha_cap if isha_astro.hour >= 23 else isha_astro

        night_start = maghrib
        night_end = prayer_times.fajr + timedelta(days=1)
        night_duration = night_end - night_start
        tahajjud = night_start + (night_duration * 2 / 3)
        if tahajjud.second > 0:
            tahajjud += timedelta(minutes=1)
        tahajjud = tahajjud.replace(second=0, microsecond=0)

        prayer_start = {
            "fajr": prayer_times.fajr,
            "dhuhr": prayer_times.dhuhr,
            "asr": prayer_times.asr,
            "maghrib": maghrib,
            "isha": isha,
            "tahajjud": tahajjud
        }
        prayer_end = {
            "fajr": prayer_times.sunrise,
            "dhuhr": prayer_times.asr,
            "asr": maghrib,
            "maghrib": maghrib_end,
            "isha": prayer_times.fajr,
            "tahajjud": prayer_times.fajr
        }

    # Common reminder times (20 mins before end)
    prayer_reminder = {
        name: (end_time - timedelta(minutes=20)).replace(second=0, microsecond=0)
        for name, end_time in prayer_end.items()
    }
    return prayer_start, prayer_end, prayer_reminder


# 🔁 Loop
def run_reminder_loop():
    current_day = datetime.now(TIMEZONE).date()
    prayer_start, prayer_end, prayer_reminder = calculate_prayer_times()
    send_daily_prayer_summary(prayer_start, prayer_end, current_day)

    while True:
        now = datetime.now(TIMEZONE).replace(second=0, microsecond=0)
        now_str = now.strftime('%H:%M')

        # ⏰ Daily reset + summary at 00:01
        if datetime.now(TIMEZONE).date() != current_day or now_str == "00:01":
            current_day = datetime.now(TIMEZONE).date()
            prayer_start, prayer_end, prayer_reminder = calculate_prayer_times()
            send_daily_prayer_summary(prayer_start, prayer_end, current_day)

        # ⏳ Reminders
        for name, reminder_time in prayer_reminder.items():
            if now_str == reminder_time.strftime('%H:%M'):
                msg = f"🔔 Reminder: {name.title()} ends soon at {prayer_end[name].strftime('%H:%M')}"
                print(msg)
                send_telegram_message(msg)

        for name, start_time in prayer_start.items():
            if now_str == start_time.strftime('%H:%M'):
                msg = f"⏰ {name.title()} has started: {start_time.strftime('%H:%M')}"
                print(msg)
                send_telegram_message(msg)

        for name, end_time in prayer_end.items():
            if now_str == end_time.strftime('%H:%M'):
                msg = f"🚨 {name.title()} has ended: {end_time.strftime('%H:%M')}"
                print(msg)
                send_telegram_message(msg)

        time.sleep(60)


# ▶️ Run
if __name__ == "__main__":
    run_reminder_loop()