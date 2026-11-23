# בוט התראות לתור פנוי אצל פרופ' דוד סוריאנו. לא קובע תור ולא שומר פרטים אישיים.
import json, os, re
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

BOOKING_URL = ("https://www.tor4you.co.il/edstn.asp?siteid=3991&sid=AAFB2DF60A86CBFE"
               "&serviceid=102084&staffid=1748")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STOP_AT = (2027, 3)   # בודק את החודשים שלפני מרץ 2027
STATE_FILE = Path(__file__).with_name("tor_bot_state.json")
MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי",
          "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
HEADER_RE = re.compile(r"(" + "|".join(MONTHS) + r")\s+(\d{4})")
NO_SLOTS = "לא נמצאו תורים פנויים בחודש זה"
# --- סוף חלק 1 ---


def notify(title, message, priority="high"):
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode("utf-8"),
                  headers={"Title": title.encode("utf-8"), "Priority": priority,
                           "Click": BOOKING_URL, "Tags": "calendar"}, timeout=15)


def month_name(ym):
    return f"{MONTHS[ym[1] - 1]} {ym[0]}"


def read_month(frame):
    try:
        text = frame.inner_text("body", timeout=5000)
    except Exception:
        return None, ""
    m = HEADER_RE.search(text)
    if not m:
        return None, text
    return (int(m.group(2)), MONTHS.index(m.group(1)) + 1), text


def find_calendar(page):
    for _ in range(20):
        for frame in page.frames:
            ym, text = read_month(frame)
            if ym:
                return frame, ym, text
        page.wait_for_timeout(1000)
    return None, None, ""


FIND_ARROWS_JS = """() => {
  const out = [];
  const arrows = ['<','>','‹','›','«','»','◄','►','◀','▶','❮','❯','<<','>>','→','←'];
  document.querySelectorAll('a,button,span,div,img,td,th,i,input,svg').forEach((e, i) => {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const t = ((e.innerText || e.value || '') + '').trim();
    const cls = typeof e.className === 'string' ? e.className : '';
    const attrs = [e.title, e.getAttribute('aria-label'), e.getAttribute('alt'), cls,
                   e.getAttribute('src'), e.id, e.getAttribute('onclick')].join(' ').toLowerCase();
    if (arrows.includes(t) || /הבא|הקודם|next|prev|arrow|forward|back|month/.test(attrs)) {
      e.setAttribute('data-torbot', i);
      out.push({key: t + '|' + attrs.slice(0, 120), id: i});
    }
  });
  return out;
}"""
# --- סוף חלק 2 ---


def next_month(ym):
    return (ym[0] + 1, 1) if ym[1] == 12 else (ym[0], ym[1] + 1)


def click_and_wait(page, frame, cand_id, ym):
    try:
        frame.click(f'[data-torbot="{cand_id}"]', timeout=5000)
    except Exception:
        return None, None, ""
    for _ in range(10):
        page.wait_for_timeout(1000)
        frame2, ym2, text = find_calendar_quick(page)
        if ym2 and ym2 != ym:
            page.wait_for_timeout(2000)
            frame2, ym2, text = find_calendar_quick(page)
            return frame2, ym2, text
    return None, None, ""


def find_calendar_quick(page):
    for frame in page.frames:
        ym, text = read_month(frame)
        if ym:
            return frame, ym, text
    return None, None, ""


def scan(browser):
    page = browser.new_page(locale="he-IL")
    try:
        page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=90000)
    except Exception:
        pass
    frame, ym, text = find_calendar(page)
    if not ym:
        return None, "לא נמצא לוח שנה בדף"
    results = {}
    while ym < STOP_AT:
        results[ym] = NO_SLOTS not in text
        print(month_name(ym), "יש תורים" if results[ym] else "אין תורים")
        target = next_month(ym)
        if target >= STOP_AT:
            break
        cands = frame.evaluate(FIND_ARROWS_JS)
        moved = False
        for c in cands:
            frame2, ym2, text2 = click_and_wait(page, frame, c["id"], ym)
            if ym2 == target:
                frame, ym, text, moved = frame2, ym2, text2, True
                break
            if ym2:   # עבר לחודש הלא נכון - מתחילים מחדש מהדף
                page.close()
                return scan_again(browser, results, c["key"])
        if not moved:
            keys = "; ".join(c["key"][:40] for c in cands[:8])
            return results, f"לא הצלחתי לעבור ל{month_name(target)}. כפתורים: {keys}"
    page.close()
    return results, ""
# --- סוף חלק 3 ---


import time
CHECK_EVERY_SECONDS = 60
RUN_MINUTES = float(os.environ.get("RUN_MINUTES", "55"))


def scan_again(browser, results, bad_key):
    page = browser.new_page(locale="he-IL")
    try:
        page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=90000)
    except Exception:
        pass
    frame, ym, text = find_calendar(page)
    while ym and next_month(ym) < STOP_AT:
        target = next_month(ym)
        cands = [c for c in frame.evaluate(FIND_ARROWS_JS) if c["key"] != bad_key]
        moved = False
        for c in cands:
            frame2, ym2, text2 = click_and_wait(page, frame, c["id"], ym)
            if ym2 == target:
                frame, ym, text, moved = frame2, ym2, text2, True
                results[ym] = NO_SLOTS not in text
                print(month_name(ym), "יש תורים" if results[ym] else "אין תורים")
                break
            if ym2:
                break
        if not moved:
            return results, f"לא הצלחתי לעבור ל{month_name(target)}"
    page.close()
    return results, ""


def check(browser, known):
    try:
        results, error = scan(browser)
    finally:
        for ctx in browser.contexts:
            ctx.close()
    if results is None:
        print("error:", error)
        return known
    with_slots = sorted(f"{y}-{m:02d}" for (y, m), has in results.items() if has)
    new = [s for s in with_slots if s not in known]
    if new:
        names = ", ".join(month_name(tuple(map(int, s.split("-")))) for s in new)
        notify("התפנה תור מוקדם!", f"יש תור פנוי ב{names}. לחצי כאן כדי לקבוע.", priority="urgent")
    if error:
        print("error:", error)
        return sorted(set(known) | set(with_slots))
    return with_slots


def main():
    state = json.loads(STATE_FILE.read_text("utf-8")) if STATE_FILE.exists() else {}
    known = state.get("months", [])
    end = time.time() + RUN_MINUTES * 60
    with sync_playwright() as p:
        browser = p.chromium.launch()
        while True:
            start = time.time()
            try:
                known = check(browser, known)
            except Exception as e:
                print("שגיאה:", str(e)[:200])
            STATE_FILE.write_text(json.dumps({"months": known}), encoding="utf-8")
            if time.time() + CHECK_EVERY_SECONDS > end:
                break
            time.sleep(max(5, CHECK_EVERY_SECONDS - (time.time() - start)))
        browser.close()


if __name__ == "__main__":
    main()
