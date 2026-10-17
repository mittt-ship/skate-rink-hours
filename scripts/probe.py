"""取得テスト（実装前の動作確認用）。

確認すること:
  1. Googleカレンダー3施設（MAO RINK・田中貴金属・埼玉）の公開iCalが取れるか
  2. 銀河アリーナのPDF（Googleドライブ）と三井不動産アイスパーク船橋のPDFが取れるか
  3. 手入力用スプレッドシートのCSVが取れるか
  4. APIキーが使えるか、PDF 2つをAIで読んでメイン/サブを区別できるか

結果は probe_results/ に保存し、GitHub Actions の実行結果ページ（Summary）にも表示する。
"""

import base64
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path("probe_results")
OUT.mkdir(exist_ok=True)

JST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(JST).date()

UA = "skate-rink-hours/0.1 (family schedule viewer; github.com/mittt-ship/skate-rink-hours)"

CALENDARS = {
    "maorink_a": "c_ea6c59fa692ce51598f302a532ac385cc0d40417042062563ee0c7480a1f0b12@group.calendar.google.com",
    "maorink_b": "c_fe3ebb95b614c5d5fbbadc6867b6b8ced6e92d963a79a4cc7d4a108248957b53@group.calendar.google.com",
    "tatsumi": "16d8c7e8b66690b04a5560bb6f4cee05fe1ddb7746cf601c0d4257d34f109b26@group.calendar.google.com",
    "saitama_a": "fif59i004jvb6c9nputlrkk7k4@group.calendar.google.com",
    "saitama_b": "qba6s4h3h601hfg86b7i1ruq14@group.calendar.google.com",
}

PDFS = {
    "ginga_2610": "https://drive.google.com/uc?export=download&id=1CtEAf9yxnohaQAaGc1M6CVTtclOvQFXW",
    "mfice_2610": "https://mf-ice.com/wp-content/uploads/2026/09/%E4%B8%80%E8%88%AC%E5%96%B6%E6%A5%AD%E3%82%AB%E3%83%AC%E3%83%B3%E3%83%80%E3%83%BC2026.10.pdf",
}

SHEET_CSV = os.environ.get("MANUAL_SHEET_CSV_URL", "")

report = []


def log(line=""):
    print(line)
    report.append(line)


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, res.headers.get("Content-Type", ""), res.read()


def unfold_ics(text):
    return re.sub(r"\r?\n[ \t]", "", text)


def parse_ics(text):
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold_ics(text), re.S):
        ev = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            ev[key.split(";")[0]] = val.strip()
        events.append(ev)
    return events


def ics_date(value):
    m = re.match(r"(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?", value or "")
    if not m:
        return None, ""
    y, mo, d, hh, mm = m.groups()
    day = dt.date(int(y), int(mo), int(d))
    if hh is None:
        return day, "終日"
    t = dt.datetime(day.year, day.month, day.day, int(hh), int(mm))
    if value.endswith("Z"):
        t = t.replace(tzinfo=dt.timezone.utc).astimezone(JST)
        day = t.date()
    return day, t.strftime("%H:%M")


def probe_calendars():
    log("## 1. Googleカレンダー")
    for name, cid in CALENDARS.items():
        url = f"https://calendar.google.com/calendar/ical/{cid.replace('@', '%40')}/public/basic.ics"
        try:
            status, ctype, body = fetch(url)
        except urllib.error.HTTPError as e:
            log(f"- **{name}**: 取得失敗 HTTP {e.code}")
            continue
        except Exception as e:  # noqa: BLE001
            log(f"- **{name}**: 取得失敗 {type(e).__name__}: {e}")
            continue
        text = body.decode("utf-8", "replace")
        (OUT / f"{name}.ics").write_text(text, encoding="utf-8")
        events = parse_ics(text)
        has_rrule = sum(1 for e in events if "RRULE" in e)
        log(f"- **{name}**: OK（イベント {len(events)} 件、繰り返し設定 {has_rrule} 件）")
        upcoming = []
        for e in events:
            day, start = ics_date(e.get("DTSTART"))
            _, end = ics_date(e.get("DTEND"))
            if day and TODAY <= day <= TODAY + dt.timedelta(days=7):
                upcoming.append((day, start, end, e.get("SUMMARY", "")))
        for day, start, end, summary in sorted(upcoming)[:20]:
            log(f"    - {day} {start}–{end} {summary}")
        if not upcoming:
            log("    - （今後7日間のイベントなし）")
    log()


def probe_pdfs():
    log("## 2. PDF")
    saved = {}
    for name, url in PDFS.items():
        try:
            status, ctype, body = fetch(url, timeout=60)
        except Exception as e:  # noqa: BLE001
            log(f"- **{name}**: 取得失敗 {type(e).__name__}: {e}")
            continue
        is_pdf = body[:4] == b"%PDF"
        log(f"- **{name}**: HTTP {status}, {ctype}, {len(body):,} bytes, PDF判定={'OK' if is_pdf else 'NG'}")
        if is_pdf:
            path = OUT / f"{name}.pdf"
            path.write_bytes(body)
            saved[name] = path
        else:
            (OUT / f"{name}.html").write_bytes(body[:20000])
    log()
    return saved


def probe_sheet():
    log("## 3. 手入力用スプレッドシート")
    if not SHEET_CSV:
        log("- URL未設定")
        log()
        return
    try:
        status, ctype, body = fetch(SHEET_CSV)
        text = body.decode("utf-8-sig", "replace")
        (OUT / "manual_sheet.csv").write_text(text, encoding="utf-8")
        rows = [r for r in text.splitlines() if r.strip()]
        log(f"- OK（{len(rows)} 行）")
        for r in rows[:10]:
            log(f"    - `{r}`")
    except Exception as e:  # noqa: BLE001
        log(f"- 取得失敗 {type(e).__name__}: {e}")
    log()


PROMPT = """これはスケート場の一般営業（一般滑走）の月間スケジュールです。
次の点をJSONだけで答えてください。説明文は不要です。

{
  "has_main_sub_distinction": true/false,   // メインリンクとサブリンク（Aリンク/Bリンク等）を区別して書いているか
  "rink_labels": ["..."],                    // 表に出てくるリンクの呼び方
  "has_resurfacing_times": true/false,       // 整氷時間が書かれているか
  "days": [                                  // 2026年10月20日〜26日の各日
    {"date": "2026-10-20", "status": "営業|営業なし|不明",
     "sessions": [{"rink": "main|sub|不明", "start": "HH:MM", "end": "HH:MM", "note": ""}]}
  ],
  "confidence": "high|medium|low",
  "notes": "読み取りで迷った点"
}"""


def probe_ai(saved):
    log("## 4. AIによるPDF読み取り")
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        log("- APIキーが見つかりません（Secrets の ANTHROPIC_API_KEY を確認）")
        log()
        return
    for name, path in saved.items():
        payload = {
            "model": "claude-sonnet-5-5",
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                     "data": base64.b64encode(path.read_bytes()).decode()}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                data = json.loads(res.read())
        except urllib.error.HTTPError as e:
            log(f"- **{name}**: API失敗 HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
            continue
        text = "".join(b.get("text", "") for b in data.get("content", []))
        (OUT / f"{name}_ai.txt").write_text(text, encoding="utf-8")
        usage = data.get("usage", {})
        log(f"- **{name}**: OK（入力 {usage.get('input_tokens')} / 出力 {usage.get('output_tokens')} トークン）")
        log("```json")
        log(text.strip().removeprefix("```json").removesuffix("```").strip())
        log("```")
    log()


def main():
    log(f"# 取得テスト結果（{dt.datetime.now(JST):%Y-%m-%d %H:%M} JST）")
    log()
    probe_calendars()
    saved = probe_pdfs()
    probe_sheet()
    probe_ai(saved)
    md = "\n".join(report)
    (OUT / "report.md").write_text(md, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md + "\n")


if __name__ == "__main__":
    main()
