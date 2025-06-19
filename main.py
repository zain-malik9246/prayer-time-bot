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

# Constants
LATITUDE = float(os.environ["LATITUDE"])
LONGITUDE = float(os.environ["LONGITUDE"])
TIMEZONE = ZoneInfo(os.environ["TIMEZONE"])


# 📨 Telegram Message Sender
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
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram error: {e}")


# 📩 Daily Summary Sender
def send_daily_prayer_summary(prayer_start, prayer_end, today):
    """
    Sends a neatly aligned prayer-time table.
    ── column width is fixed (24 chars) so the HH:MM values line up,
       no matter how wide each emoji or label is rendered.
    """
    COL = 24  # characters to pad before the time

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


# 🕰️ Prayer Calculation
def calculate_prayer_times():
    today = date.today()
    location = (LATITUDE, LONGITUDE)

    params = CalculationParameters(
        fajr_angle=18,
        isha_angle=17,
        method=CalculationMethod.MUSLIM_WORLD_LEAGUE)
    params.madhab = Madhab.HANAFI
    params.high_latitude_rule = HighLatitudeRule.TWILIGHT_ANGLE

    prayer_times = PrayerTimes(location,
                               today,
                               calculation_parameters=params,
                               time_zone=TIMEZONE)

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

    now_plus_5 = (datetime.now(TIMEZONE) + timedelta(minutes=5)).replace(second=0, microsecond=0)
    prayer_start = {
        "fajr": prayer_times.fajr,
        "dhuhr": prayer_times.dhuhr,
        "asr": prayer_times.asr,
        "maghrib": now_plus_5,
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

    prayer_reminder = {
        name: (end_time - timedelta(minutes=20)).replace(second=0,
                                                         microsecond=0)
        for name, end_time in prayer_end.items()
    }

    return prayer_start, prayer_end, prayer_reminder


# 🔁 Loop
def run_reminder_loop():
    current_day = date.today()
    prayer_start, prayer_end, prayer_reminder = calculate_prayer_times()
    send_daily_prayer_summary(prayer_start, prayer_end, current_day)

    while True:
        now = datetime.now(TIMEZONE).replace(second=0, microsecond=0)
        now_str = now.strftime('%H:%M')

        # ⏰ Daily reset + summary at 00:01
        if date.today() != current_day or now_str == "00:01":
            current_day = date.today()
            prayer_start, prayer_end, prayer_reminder = calculate_prayer_times(
            )
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
