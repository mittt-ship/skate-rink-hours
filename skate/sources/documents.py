"""PDF・画像型（AIで読む）：船橋・KOSÉ新横浜・横浜銀行・銀河・小瀬・東大和。
お知らせ型（AIで変更点を拾う）：宇都宮・アクアリンクちば。
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import urllib.parse

from bs4 import BeautifulSoup

from .. import ai
from ..common import (
    CLOSED, CONFIRMED, OFF_SEASON, OPEN, UNKNOWN, UNPUBLISHED, DayRecord, Session, date_range,
    fetch_bytes, fetch_text, normalize, open_day, simple_day,
)

SCHEDULE_PROMPT = """これはスケート場「{name}」の一般営業（一般滑走・一般開放）の月間スケジュールです。
{year}年{month}月の各日について、一般の人が予約なしで滑れる時間帯を読み取り、JSONだけを返してください。説明文は不要です。

施設についての注意：
{hints}

ルール：
- 貸切・大会・教室・クラブ・専用利用の時間は一般営業に含めない
- 「一般滑走休み」「一般利用不可」「休館」などの日は status を "closed" にする
- 読み取れない・書かれていない日は status を "unknown" にする（推測しない）
- 時刻は "HH:MM"（24時間表記）。整氷の時刻は resurfacing に開始時刻だけを入れる
- {month}月1日から月末まで、すべての日を days に入れる

出力形式：
{{
  "year": {year}, "month": {month},
  "days": [
    {{"date": "{year}-{month:02d}-01", "status": "open|closed|unknown",
      "sessions": [{{"rink": "main|sub", "start": "HH:MM", "end": "HH:MM", "note": ""}}],
      "resurfacing": [], "note": ""}}
  ],
  "confidence": "high|medium|low",
  "notes": "読み取りで迷った点"
}}"""

HINTS = {
    "mfice": "リンクは2面。表の「Aリンク」がメイン（main、60m×30m）、「Bリンク」がサブ（sub）。",
    "shinyoko": "リンクは1面（rink はすべて main）。「一般滑走」と書かれた日の時間帯だけを読む。「貸切」「一般滑走休み」は closed。「整氷 ① 12:00～ ② 14:00～」のような整氷の開始時刻は resurfacing に入れる。",
    "yokohama": "サブリンクは極小のため無視し、rink はすべて main。一般滑走の営業時間・整氷時間・休業日が書かれている。ワンポイントレッスンは note に入れる。",
    "ginga": "サブリンクは極小のため無視し、rink はすべて main。一般利用の時間帯を読む。学校の教室などでリンクの一部を使う時間帯は note に入れる。",
    "kosesp": "リンクは1面（rink はすべて main）。「一般利用不可」は closed。",
    "higashiyamato": "リンクは1面（rink はすべて main）。カレンダー画像。一般滑走の時間帯を読む。",
}

NEWS_PROMPT = """これはスケート場「{name}」のお知らせ欄の文章です（今日は{today}）。
スケートリンクの一般営業（一般滑走・一般開放）について、通常と違う日（終日貸切・休館・時間短縮・時間変更・特別営業など）を、
{today}から{end}までの範囲で抜き出し、JSONだけを返してください。説明文は不要です。

通常の営業時間：{normal}

ルール：
- 教室やイベントの募集だけで、一般営業の時間が変わらないものは含めない
- 時刻は "HH:MM"（24時間表記）。終日営業しない日は status を "closed"、時間が変わる日は "open" にして sessions に新しい時間を入れる
- 年が書かれていない日付は、今日に最も近い未来の日付として解釈する

出力形式：
{{"exceptions": [{{"date": "YYYY-MM-DD", "status": "open|closed",
  "sessions": [{{"rink": "main", "start": "HH:MM", "end": "HH:MM", "note": ""}}], "note": "理由など"}}]}}"""


# ---------------------------------------------------------------- 月ごとのドキュメントを探す

def _abs(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def _drive_download(url: str) -> str:
    m = re.search(r"/file/d/([\w-]+)", url)
    return f"https://drive.google.com/uc?export=download&id={m.group(1)}" if m else url


def find_documents(rink_id: str, today: dt.date) -> list[tuple[int, int, str, str]]:
    """(年, 月, URL, media_type) の一覧。"""
    docs = []
    if rink_id == "mfice":
        base = "https://mf-ice.com/"
        html = fetch_text(base)
        for m in set(re.finditer(r"(https?://mf-ice\.com/wp-content/uploads/[^\"'\s<>]*?一般営業カレンダー(\d{4})\.(\d{1,2})\.pdf)", html)):
            docs.append((int(m.group(2)), int(m.group(3)), m.group(1), "application/pdf"))
    elif rink_id == "shinyoko":
        base = "https://www.princehotels.co.jp/skate/shinyokohama/general.html"
        html = fetch_text(base)
        for href, yy, mm in set(re.findall(r"((?:https?://[^\"'\s]+/)?pdf/g_schedule_(\d{2})(\d{2})\.pdf)", html)):
            docs.append((2000 + int(yy), int(mm), _abs(base, href), "application/pdf"))
    elif rink_id == "yokohama":
        base = "https://yokohama-icearena.jp/topics/?p=8216"
        soup = BeautifulSoup(fetch_text(base), "html.parser")
        for a in soup.find_all("a", href=True):
            m = re.search(r"(\d{4})年(\d{1,2})月", normalize(a.get_text()))
            if m and a["href"].lower().endswith(".pdf"):
                docs.append((int(m.group(1)), int(m.group(2)), _abs(base, a["href"]), "application/pdf"))
    elif rink_id == "ginga":
        base = "https://ginga-arena.sagamiharashi-machimidori.or.jp/%E3%82%A2%E3%82%A4%E3%82%B9%E3%82%B9%E3%82%B1%E3%83%BC%E3%83%88%E5%A0%B4/%E4%B8%80%E8%88%AC%E5%88%A9%E7%94%A8"
        soup = BeautifulSoup(fetch_text(base), "html.parser")
        for a in soup.find_all("a", href=True):
            href = urllib.parse.unquote(a["href"])
            m = re.search(r"令和(\d{1,2})年(\d{1,2})月", normalize(a.get_text()))
            if m and "drive.google.com/file/d/" in href:
                fid = re.search(r"drive\.google\.com/file/d/[\w-]+", href).group(0)
                docs.append((2018 + int(m.group(1)), int(m.group(2)), _drive_download("https://" + fid), "application/pdf"))
    elif rink_id == "kosesp":
        base = "https://www.kose-sp.pref.yamanashi.jp/info/use/216606/"
        soup = BeautifulSoup(fetch_text(base), "html.parser")
        for a in soup.find_all("a", href=True):
            t = normalize(a.get_text())
            m = re.search(r"R(\d{1,2})\.?\s*(\d{1,2})月.*一般利用", t)
            if m and a["href"].lower().endswith(".pdf"):
                docs.append((2018 + int(m.group(1)), int(m.group(2)), _abs(base, a["href"]), "application/pdf"))
    elif rink_id == "higashiyamato":
        base = "https://www.seibu-leisure.co.jp/web/iceskate/index.html"
        html = fetch_text(base)
        for href, yy, mm in set(re.findall(r"((?:https?://[^\"'\s]+)?/image/skating_schedule(\d{2})(\d{2})\.png)", html)):
            docs.append((2000 + int(yy), int(mm), _abs(base, href), "image/png"))
    # 今月以降だけ（過去月は保存済みの記録を残す）
    this_month = (today.year, today.month)
    return sorted({d for d in docs if (d[0], d[1]) >= this_month})


# ---------------------------------------------------------------- AIの結果を1日分のレコードにする

def _records_from_ai(result: dict, year: int, month: int, url: str) -> dict:
    out = {}
    conf = result.get("confidence", "medium")
    if conf not in ("high", "medium", "low"):
        conf = "medium"
    for item in result.get("days", []):
        try:
            day = dt.date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        if (day.year, day.month) != (year, month):
            continue
        status = item.get("status")
        sessions = [Session(s.get("start", ""), s.get("end", ""), "sub" if s.get("rink") == "sub" else "main",
                            s.get("note", "") or "")
                    for s in item.get("sessions", []) if s.get("start") and s.get("end")]
        note = item.get("note", "") or ""
        if status == "open" and sessions:
            out[day] = open_day(sessions, url, note=note, confidence=conf,
                                resurfacing=[r for r in item.get("resurfacing", []) if r])
        elif status == "closed":
            out[day] = simple_day(CLOSED, url, note or "一般営業なし", confidence=conf)
        else:
            out[day] = simple_day(UNKNOWN, url, note or "読み取れませんでした。公式サイトで確認してください",
                                  confidence="low")
    return out


def fetch_monthly(rink: dict, start: dt.date, end: dt.date, today: dt.date, season=None) -> dict:
    rid, url = rink["id"], rink["schedule_url"]
    found: dict = {}
    covered_months = set()
    for year, month, doc_url, media in find_documents(rid, today):
        payload = fetch_bytes(doc_url, timeout=60)
        if media == "application/pdf" and payload[:4] != b"%PDF":
            raise RuntimeError(f"PDFではないファイルが返りました：{doc_url}")
        prompt = SCHEDULE_PROMPT.format(name=rink["name"], year=year, month=month, hints=HINTS.get(rid, ""))
        result = ai.read(rid, payload, media, prompt, today)
        found.update(_records_from_ai(result, year, month, doc_url if media != "image/png" else url))
        covered_months.add((year, month))
    out = {}
    for d in date_range(start, end):
        if season and not season(d):
            out[d] = simple_day(OFF_SEASON, url, "営業期間外")
        elif d in found:
            out[d] = found[d]
        elif (d.year, d.month) in covered_months:
            out[d] = simple_day(UNKNOWN, url, "読み取れませんでした。公式サイトで確認してください", confidence="low")
        else:
            out[d] = simple_day(UNPUBLISHED, url, "まだ公開されていません")
    return out


# ---------------------------------------------------------------- お知らせから変更点を拾う

NEWS_SOURCES = {
    "utsunomiya": ("https://www.miya-sp.jp/topics/news/", ".news_box",
                   "10月〜5月。平日13:00〜19:00、土日祝9:00〜17:00。10・11・4・5月の水曜は休場"),
    "aqua": ("http://www.aquarink-chiba.jp/news01/news.php", "li",
             "毎日9:00〜18:00"),
}


def apply_news_exceptions(rink: dict, planned: dict, today: dt.date, end: dt.date) -> dict:
    rid = rink["id"]
    page_url, selector, normal = NEWS_SOURCES[rid]
    soup = BeautifulSoup(fetch_text(page_url), "html.parser")
    blocks = [normalize(b.get_text(" ")) for b in soup.select(selector)]
    text = "\n\n".join(b for b in blocks if b)[:12000]
    if not text:
        return planned
    prompt = NEWS_PROMPT.format(name=rink["name"], today=today.isoformat(), end=end.isoformat(), normal=normal)
    result = ai.read(rid + "-news", text.encode(), "text/plain", prompt, today)
    out = dict(planned)
    for ex in result.get("exceptions", []):
        try:
            day = dt.date.fromisoformat(ex["date"])
        except (KeyError, ValueError):
            continue
        if day not in out or out[day].status == OFF_SEASON:
            continue
        note = (ex.get("note") or "").strip() or "お知らせ欄の情報"
        if ex.get("status") == "closed":
            out[day] = simple_day(CLOSED, page_url, note, confidence="medium")
        else:
            sessions = [Session(s["start"], s["end"], "main", s.get("note", "") or "")
                        for s in ex.get("sessions", []) if s.get("start") and s.get("end")]
            if sessions:
                out[day] = open_day(sessions, page_url, note=note, confidence="medium")
    return out
