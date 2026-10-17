"""Googleカレンダー型：MAO RINK・田中貴金属・埼玉。

公開カレンダーのiCalデータを取得し、繰り返し設定を日付に展開して読む。
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import icalendar
import recurring_ical_events

from ..common import (
    CLOSED, OPEN, UNPUBLISHED, DayRecord, Session, date_range, fetch_bytes, find_time_ranges,
    normalize, simple_day,
)

ICAL_URL = "https://calendar.google.com/calendar/ical/{}/public/basic.ics"

CAL_IDS = {
    "maorink_main": "c_fe3ebb95b614c5d5fbbadc6867b6b8ced6e92d963a79a4cc7d4a108248957b53@group.calendar.google.com",
    "maorink_sub": "c_ea6c59fa692ce51598f302a532ac385cc0d40417042062563ee0c7480a1f0b12@group.calendar.google.com",
    "tatsumi": "16d8c7e8b66690b04a5560bb6f4cee05fe1ddb7746cf601c0d4257d34f109b26@group.calendar.google.com",
    "saitama": "qba6s4h3h601hfg86b7i1ruq14@group.calendar.google.com",
}


def load_calendar(name: str) -> bytes:
    return fetch_bytes(ICAL_URL.format(CAL_IDS[name].replace("@", "%40")))


def expand(ics: bytes, start: dt.date, end: dt.date):
    """(日付, 開始HH:MM or None, 終了HH:MM or None, 件名) の一覧を返す。"""
    cal = icalendar.Calendar.from_ical(ics)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end + dt.timedelta(days=1)):
        s = ev.get("DTSTART").dt
        e = ev.get("DTEND").dt if ev.get("DTEND") else None
        title = normalize(str(ev.get("SUMMARY", "")))
        if isinstance(s, dt.datetime):
            s_local = s.astimezone(dt.timezone(dt.timedelta(hours=9))) if s.tzinfo else s
            e_local = (e.astimezone(dt.timezone(dt.timedelta(hours=9))) if e is not None and e.tzinfo else e)
            out.append((s_local.date(), s_local.strftime("%-H:%M"),
                        e_local.strftime("%-H:%M") if e_local is not None else None, title))
        else:
            # 終日イベント（DTENDは翌日）。複数日にまたがる場合は日ごとに展開
            last = (e - dt.timedelta(days=1)) if isinstance(e, dt.date) else s
            for d in date_range(max(s, start), min(last, end)):
                out.append((d, None, None, title))
    return [x for x in out if start <= x[0] <= end]


def _build(days: dict, start: dt.date, end: dt.date, coverage_end: dt.date | None, url: str) -> dict:
    result = {}
    for d in date_range(start, end):
        info = days.get(d)
        if info and info["sessions"] and not info["all_closed"]:
            result[d] = DayRecord(OPEN, sessions=info["sessions"], note=" / ".join(info["notes"]), source_url=url)
        elif info and (info["closed"] or info["all_closed"]):
            result[d] = simple_day(CLOSED, url, " / ".join(info["notes"] + info["closed"]))
        elif coverage_end and d <= coverage_end:
            result[d] = simple_day(CLOSED, url, "一般営業の掲載なし")
        else:
            result[d] = simple_day(UNPUBLISHED, url, "まだ公開されていません")
    return result


def _empty_day():
    return {"sessions": [], "notes": [], "closed": [], "all_closed": False}


# ---------------------------------------------------------------- MAO RINK

def parse_maorink(main_ics: bytes, sub_ics: bytes, start, end, url):
    days = defaultdict(_empty_day)
    coverage = None
    for ics, default_rink in ((main_ics, "main"), (sub_ics, "sub")):
        for d, s, e, title in expand(ics, start, end):
            info = days[d]
            rink = "main" if "メイン" in title else "sub" if "サブ" in title else default_rink
            if "休館" in title:
                info["all_closed"] = True
                info["closed"].append("休館日")
            elif "貸切" in title:
                info["closed"].append(f"{'メイン' if rink == 'main' else 'サブ'}リンク終日貸切")
            elif s and e:
                note = "ナイトスケート" if "ナイト" in title else ""
                info["sessions"].append(Session(s, e, "sub" if note else rink, note))
            coverage = max(coverage or d, d)
    # 終日貸切は、そのリンクの時間帯を消す
    for info in days.values():
        for c in info["closed"]:
            if c.startswith("メイン"):
                info["sessions"] = [x for x in info["sessions"] if x.rink != "main"]
            if c.startswith("サブ"):
                info["sessions"] = [x for x in info["sessions"] if x.rink != "sub"]
    return _build(days, start, end, coverage, url)


# ---------------------------------------------------------------- 田中貴金属アイスアリーナ

_TATSUMI_IGNORE = ("スケートショップ", "小杉", "カレンダー更新")


def parse_tatsumi(ics: bytes, start, end, url):
    days = defaultdict(_empty_day)
    coverage = None
    for d, s, e, title in expand(ics, start, end):
        if any(k in title for k in _TATSUMI_IGNORE):
            continue
        info = days[d]
        if "休館" in title:
            info["all_closed"] = True
            info["closed"].append("休館日")
            continue  # 休館日だけの登録は「掲載済み」の根拠にしない
        coverage = max(coverage or d, d)
        if "一般滑走なし" in title or "専用利用" in title:
            info["closed"].append("一般滑走なし" if "一般滑走なし" in title else "終日専用利用")
            continue
        ranges = find_time_ranges(title) or ([(s, e)] if s and e else [])
        if "ナイト" in title:
            info["sessions"] += [Session(a, b, "sub", "ナイトスケート") for a, b in ranges]
        elif "メイン" in title:
            info["sessions"] += [Session(a, b, "main") for a, b in ranges]
        elif "サブ" in title:
            info["sessions"] += [Session(a, b, "sub") for a, b in ranges]
        elif ranges:
            info["sessions"] += [Session(a, b, "main", title) for a, b in ranges]
    return _build(days, start, end, coverage, url)


# ---------------------------------------------------------------- 埼玉アイスアリーナ

def parse_saitama(ics: bytes, start, end, url):
    days = defaultdict(_empty_day)
    coverage = None
    for d, s, e, title in expand(ics, start, end):
        info = days[d]
        if "全館臨時休業" in title or "一般営業お休み" in title:
            info["all_closed"] = True
            info["closed"].append(title)
            coverage = max(coverage or d, d)
        elif "メインリンクお休み" in title:
            info["closed"].append("メインリンクお休み")
        elif ("メイン" in title or "サブ" in title) and s and e:
            info["sessions"].append(Session(s, e, "main" if "メイン" in title else "sub"))
            coverage = max(coverage or d, d)
        elif "専用利用" in title:
            info["notes"].append("専用利用の時間あり")
    for info in days.values():
        if "メインリンクお休み" in info["closed"]:
            info["sessions"] = [x for x in info["sessions"] if x.rink != "main"]
            if info["sessions"]:
                info["notes"].append("メインリンクお休み")
                info["closed"].remove("メインリンクお休み")
    return _build(days, start, end, coverage, url)


# ---------------------------------------------------------------- 取得の入口

def fetch_maorink(start, end, url):
    return parse_maorink(load_calendar("maorink_main"), load_calendar("maorink_sub"), start, end, url)


def fetch_tatsumi(start, end, url):
    return parse_tatsumi(load_calendar("tatsumi"), start, end, url)


def fetch_saitama(start, end, url):
    return parse_saitama(load_calendar("saitama"), start, end, url)
