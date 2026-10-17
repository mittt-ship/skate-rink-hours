"""共通の部品：日付、取得、時間帯の読み取り、1日分のレコード。"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
import urllib.request
from dataclasses import dataclass, field, asdict

import holidays

JST = dt.timezone(dt.timedelta(hours=9))
UA = "skate-rink-hours/1.0 (family schedule viewer; +https://github.com/mittt-ship/skate-rink-hours)"

_JP_HOLIDAYS = holidays.country_holidays("JP")

# 状態の種類（画面の表示名は index.html 側で付ける）
OPEN = "open"                # 営業
CLOSED = "closed"            # 営業なし
OFF_SEASON = "off_season"    # 期間外
UNPUBLISHED = "unpublished"  # 未掲載
UNKNOWN = "unknown"          # 不明・取得準備中

CONFIRMED = "confirmed"  # 公式の掲載内容から取得
PLANNED = "planned"      # 基本営業時間などから推定した「予定」


def now_jst() -> dt.datetime:
    return dt.datetime.now(JST).replace(microsecond=0)


def today_jst() -> dt.date:
    return now_jst().date()


def end_of_next_month(day: dt.date) -> dt.date:
    first_next = (day.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    first_after = (first_next + dt.timedelta(days=32)).replace(day=1)
    return first_after - dt.timedelta(days=1)


def date_range(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def is_holiday(day: dt.date) -> bool:
    return day in _JP_HOLIDAYS


def is_weekend_or_holiday(day: dt.date) -> bool:
    return day.weekday() >= 5 or is_holiday(day)


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def fetch_text(url: str, timeout: int = 30, encoding: str = "utf-8") -> str:
    return fetch_bytes(url, timeout).decode(encoding, "replace")


def normalize(text: str) -> str:
    """半角カナ・全角英数字を揃え、空白を詰める。"""
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


_TIME_RANGE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})\s*[~〜～\-－–—ー]\s*(\d{1,2})\s*[:：]\s*(\d{2})")


def find_time_ranges(text: str) -> list[tuple[str, str]]:
    out = []
    for h1, m1, h2, m2 in _TIME_RANGE.findall(normalize(text)):
        out.append((f"{int(h1)}:{m1}", f"{int(h2)}:{m2}"))
    return out


@dataclass
class Session:
    start: str
    end: str
    rink: str = "main"   # main / sub
    note: str = ""


@dataclass
class DayRecord:
    status: str
    basis: str = CONFIRMED
    sessions: list[Session] = field(default_factory=list)
    resurfacing: list[str] = field(default_factory=list)
    confidence: str = "high"
    note: str = ""
    source_url: str = ""

    def to_json(self, fetched_at: str) -> dict:
        sessions = sorted(
            {(s.rink, s.start, s.end, s.note): s for s in self.sessions}.values(),
            key=lambda s: (s.rink != "main", _minutes(s.start)),
        )
        data = asdict(self)
        data["sessions"] = [asdict(s) for s in sessions]
        data["main_open"] = self.status == OPEN and any(s.rink == "main" for s in sessions)
        data["fetched_at"] = fetched_at
        return data


def _minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return 0


def open_day(sessions, source_url, basis=CONFIRMED, note="", confidence="high", resurfacing=None) -> DayRecord:
    return DayRecord(OPEN, basis, list(sessions), list(resurfacing or []), confidence, note, source_url)


def closed_day(source_url, note="", basis=CONFIRMED, confidence="high") -> DayRecord:
    return DayRecord(CLOSED, basis, [], [], confidence, note, source_url)


def simple_day(status, source_url, note="", basis=CONFIRMED, confidence="high") -> DayRecord:
    return DayRecord(status, basis, [], [], confidence, note, source_url)


def in_season(day: dt.date, start_md: tuple[int, int], end_md: tuple[int, int]) -> bool:
    """毎年の営業期間（例：10/1〜5/15）に入っているか。年をまたぐ期間にも対応。"""
    md = (day.month, day.day)
    if start_md <= end_md:
        return start_md <= md <= end_md
    return md >= start_md or md <= end_md
