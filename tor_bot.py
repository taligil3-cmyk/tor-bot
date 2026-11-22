# בוט התראות לתור פנוי אצל פרופ' דוד סוריאנו. לא קובע תור ולא שומר פרטים אישיים.
import hashlib, json, os, re
from datetime import date, datetime
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

BOOKING_URL = ("https://www.tor4you.co.il/edstn.asp?siteid=3991&sid=AAFB2DF60A86CBFE"
               "&serviceid=102084&staffid=1748")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
ONLY_BEFORE = None  # למשל "2027-03-01" כדי לקבל התראה רק על תורים לפני התאריך הזה

STATE_FILE = Path(__file__).with_name("tor_bot_state.json")
DATE_RE = re.compile(r"(?<![\d:])(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d:])")
NO_SLOTS_HINTS = ["אין תורים", "לא נמצאו תורים", "אין מועדים"]


def notify(title, message, priority="high"):
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode("utf-8"),
                  headers={"Title": title.encode("utf-8"), "Priority": priority,
                           "Click": BOOKING_URL, "Tags": "calendar"}, timeout=15)


def read_page_text():
    error = ""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="he-IL")
        try:
            page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            error = str(e).splitlines()[0][:200]
