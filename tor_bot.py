# בוט התראות לתור פנוי אצל פרופ' דוד סוריאנו. לא קובע תור ולא שומר פרטים אישיים.
import hashlib, json, os, re
from datetime import date, datetime
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

BOOKING_URL = ("https://www.tor4you.co.il/edstn.asp?siteid=3991&sid=AAFB2DF60A86CBFE"
               "&serviceid=102084&staffid=1748")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
ONLY_BEFORE = None  # למשל "2027-02-15" כדי לקבל התראה רק על תורים לפני התאריך הזה

STATE_FILE = Path(__file__).with_name("tor_bot_state.json")
DATE_RE = re.compile(r"(?<![\d:])(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d:])")
NO_SLOTS_HINTS = ["אין תורים", "לא נמצאו תורים", "אין מועדים"]


def notify(title, message, priority="high"):
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode("utf-8"),
                  headers={"Title": title.encode("utf-8"), "Priority": priority,
                           "Click": BOOKING_URL, "Tags": "calendar"}, timeout=15)


def read_page_text():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="he-IL")
        page.goto(BOOKING_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)
        texts = []
        for frame in page.frames:
            try:
                texts.append(frame.inner_text("body", timeout=5000))
            except Exception:
                pass
        browser.close()
    return "\n".join(texts)


def extract_dates(text):
    today, found = date.today(), set()
    for d, m, y in DATE_RE.findall(text):
        d, m = int(d), int(m)
        if y:
            y = int(y) + (2000 if int(y) < 100 else 0)
        else:
            y = today.year if (m, d) >= (today.month, today.day) else today.year + 1
        try:
            dt = date(y, m, d)
        except ValueError:
            continue
        if today <= dt <= date(today.year + 2, 12, 31):
            found.add(dt)
    if ONLY_BEFORE:
        found = {dt for dt in found if dt < date.fromisoformat(ONLY_BEFORE)}
    return found


def fmt(dates):
    return ", ".join(d.strftime("%d/%m/%Y") for d in sorted(dates)[:6])


def main():
    text = read_page_text()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    dates = extract_dates(text)
    no_slots = any(h in text for h in NO_SLOTS_HINTS)

    if not STATE_FILE.exists():
        snippet = " ".join(text.split())[:700]
        msg = (f"הבוט פועל. תאריכים שמופיעים עכשיו: {fmt(dates)}" if dates
               else f"הבוט פועל, אבל לא זיהה תאריכים. תחילת הדף: {snippet}")
        notify("בוט התורים הופעל", msg, priority="default")
    else:
        old = {date.fromisoformat(s) for s in json.loads(STATE_FILE.read_text("utf-8"))["dates"]}
        new = dates - old
        if new and not no_slots:
            earlier = {d for d in new if not old or d < min(old)}
            title = "התפנה תור מוקדם!" if earlier else "הופיע תאריך פנוי חדש"
            notify(title, f"תאריכים חדשים: {fmt(new)}. לחצי כאן כדי לקבוע.")
    print(datetime.now().strftime("%H:%M"), "dates:", fmt(dates))
    STATE_FILE.write_text(json.dumps({"dates": sorted(d.isoformat() for d in dates),
                                      "hash": text_hash}), encoding="utf-8")


if __name__ == "__main__":
    main()
