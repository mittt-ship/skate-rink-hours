"""基本営業時間・手入力・準備中の施設。"""

from __future__ import annotations

import csv
import datetime as dt
import io

from ..common import (
    CLOSED, OFF_SEASON, OPEN, PLANNED, UNKNOWN, CONFIRMED, DayRecord, Session, date_range, fetch_text,
    in_season, is_holiday, is_weekend_or_holiday, open_day, simple_day,
)


# ---------------------------------------------------------------- アクアリンクちば

def aqua(start, end, url):
    return {d: open_day([Session("9:00", "18:00")], url, basis=PLANNED, confidence="medium",
                        note="基本営業時間からの予定（変更はお知らせ欄で告知）")
            for d in date_range(start, end)}


# ---------------------------------------------------------------- 宇都宮市スケートセンター

def _utsunomiya_wednesday_closed(day: dt.date) -> bool:
    if day.month not in (10, 11, 4, 5):
        return False
    if day.weekday() == 2 and not is_holiday(day):
        return True
    yesterday = day - dt.timedelta(days=1)
    return yesterday.weekday() == 2 and is_holiday(yesterday)  # 水曜が祝日なら翌日休場


def utsunomiya(start, end, url):
    out = {}
    for d in date_range(start, end):
        if not in_season(d, (10, 1), (5, 15)):
            out[d] = simple_day(OFF_SEASON, url, "スケートリンクの営業は10月1日〜5月15日")
        elif (d.month, d.day) in ((12, 30), (12, 31), (1, 1)) or _utsunomiya_wednesday_closed(d):
            out[d] = simple_day(CLOSED, url, "休場日", basis=PLANNED, confidence="medium")
        else:
            hours = ("9:00", "17:00") if is_weekend_or_holiday(d) else ("13:00", "19:00")
            out[d] = open_day([Session(*hours)], url, basis=PLANNED, confidence="medium",
                              note="基本営業時間からの予定（大会などの変更はお知らせ欄で告知）")
    return out


# ---------------------------------------------------------------- 日光霧降アイスアリーナ

def _second_monday_of_may(year: int) -> dt.date:
    d = dt.date(year, 5, 1)
    first_monday = d + dt.timedelta(days=(7 - d.weekday()) % 7)
    return first_monday + dt.timedelta(days=7)


def read_manual_sheet(csv_text: str) -> dict:
    """スプレッドシート（CSV）を {施設ID: {日付: [行, ...]}} にする。"""
    data: dict = {}
    # 1行がA列の1セルにまとめて入力されていても読めるよう、セル内のカンマでもう一度分割する
    lines = []
    for cells in csv.reader(io.StringIO(csv_text)):
        if len(cells) == 1 and "," in cells[0]:
            cells = next(csv.reader([cells[0]]))
        lines.append(cells)
    if not lines:
        return data
    header = [h.strip() for h in lines[0]]
    for cells in lines[1:]:
        row = dict(zip(header, cells))
        try:
            day = dt.date.fromisoformat((row.get("date") or "").strip())
        except ValueError:
            continue
        rink = (row.get("rink_id") or "").strip()
        data.setdefault(rink, {}).setdefault(day, []).append({k: (v or "").strip() for k, v in row.items()})
    return data


def kirifuri(start, end, url, manual: dict):
    entries = manual.get("kirifuri", {})
    out = {}
    for d in date_range(start, end):
        if _second_monday_of_may(d.year) <= d <= dt.date(d.year, 6, 30):
            out[d] = simple_day(OFF_SEASON, url, "休館期間（5月第2月曜〜6月30日）")
            continue
        rows = entries.get(d)
        if rows:
            sessions = [Session(r["start"], r["end"], "main", r.get("note", ""))
                        for r in rows if r.get("start") and r.get("end")]
            words = " ".join(r.get("status", "") + " " + r.get("note", "") for r in rows)
            if not sessions and any(k in words for k in ("なし", "休", "閉", "貸切", "×", "✖")):
                out[d] = simple_day(CLOSED, url, words.replace("営業なし", "").strip() or "営業なし（手入力）")
            elif sessions:
                out[d] = open_day(sessions, url, note="手入力の営業カレンダー")
            else:
                out[d] = simple_day(UNKNOWN, url, f"手入力の時間が空欄（{words.strip() or '記入なし'}）")
        else:
            out[d] = open_day([Session("10:00", "15:30")], url, basis=PLANNED, confidence="medium",
                              note="基本営業時間からの予定（公式の営業カレンダーで確認してください）")
    return out


# ---------------------------------------------------------------- 取得準備中（PDF・画像をAIで読む施設）

PENDING_SEASONS = {
    "ginga": (dt.date(2026, 10, 20), dt.date(2027, 3, 31)),
}
PENDING_YEARLY = {
    "kosesp": ((7, 1), (3, 31)),
}


def pending(rink_id, start, end, url):
    out = {}
    for d in date_range(start, end):
        if rink_id in PENDING_SEASONS and not (PENDING_SEASONS[rink_id][0] <= d <= PENDING_SEASONS[rink_id][1]):
            out[d] = simple_day(OFF_SEASON, url, "営業期間外")
        elif rink_id in PENDING_YEARLY and not in_season(d, *PENDING_YEARLY[rink_id]):
            out[d] = simple_day(OFF_SEASON, url, "営業期間外")
        else:
            out[d] = simple_day(UNKNOWN, url, "PDFの読み取りは準備中です。公式サイトで確認してください")
    return out


def fetch_manual_sheet(csv_url: str) -> dict:
    if not csv_url:
        return {}
    return read_manual_sheet(fetch_text(csv_url, encoding="utf-8-sig"))
