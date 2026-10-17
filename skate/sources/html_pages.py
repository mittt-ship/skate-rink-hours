"""HTML型：ダイドー・江戸川・明治神宮外苑・東大和。"""

from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from ..common import (
    CLOSED, OFF_SEASON, OPEN, PLANNED, UNKNOWN, UNPUBLISHED, Session, date_range, fetch_text,
    find_time_ranges, in_season, is_weekend_or_holiday, normalize, open_day, simple_day,
)


def _month_year(month: int, today: dt.date) -> int:
    """年が書かれていない月表示を、今日を基準に年付きに直す（12月に1月が出たら翌年）。"""
    if month < today.month - 6:
        return today.year + 1
    if month > today.month + 6:
        return today.year - 1
    return today.year


# ---------------------------------------------------------------- ダイドードリンコアイスアリーナ

def parse_daido(html: str, start, end, url, today):
    soup = BeautifulSoup(html, "html.parser")
    months = [int(re.sub(r"\D", "", b.get_text())) for b in soup.select(".comp-icearena-schedule__cal-button")]
    holders = soup.select(".comp-icearena-schedule__cal-holder")
    found = {}
    for month, holder in zip(months, holders):
        year = _month_year(month, today)
        for item in holder.select('.comp-icearena-schedule__cal-item[data-type="date"]'):
            head = item.select_one(".comp-icearena-schedule__cal-item-heading .pc-only")
            if not head or not head.get_text(strip=True).isdigit():
                continue
            day = dt.date(year, month, int(head.get_text(strip=True)))
            plans = item.select(".comp-icearena-schedule__cal-plan")
            sessions, notes, closed = [], [], False
            for plan in plans:
                heading = normalize(plan.select_one(".comp-icearena-schedule__cal-plan-heading").get_text(" "))
                body_el = plan.select_one(".comp-icearena-schedule__cal-plan-contents")
                body = normalize(body_el.get_text(" ")) if body_el else ""
                if "一般滑走" in heading and "お休み" not in heading:
                    sessions += [Session(a, b) for a, b in find_time_ranges(body)]
                elif "お休み" in heading:
                    closed = True
                elif heading:
                    notes.append(heading + (f"（{body}）" if body else ""))
            if sessions:
                found[day] = open_day(sessions, url)
            elif closed:
                found[day] = simple_day(CLOSED, url, "一般営業お休み" + (f"：{' / '.join(notes)}" if notes else ""))
    last = max(found) if found else None
    return {d: found.get(d) or (simple_day(CLOSED, url, "一般営業の掲載なし") if last and d <= last
                                else simple_day(UNPUBLISHED, url, "まだ公開されていません"))
            for d in date_range(start, end)}


# ---------------------------------------------------------------- 江戸川区スポーツランド

def parse_edogawa(html: str, start, end, url, today):
    soup = BeautifulSoup(html, "html.parser")
    labels = [normalize(b.get_text()) for b in soup.select("button.edsl-tab__button")]
    tables = soup.select(".calendar-table__scroll table")
    found = {}
    for label, table in zip(labels, tables):
        m = re.match(r"(\d{2})年(\d{1,2})月", label)
        if not m:
            continue
        year, month = 2000 + int(m.group(1)), int(m.group(2))
        for row in table.select("tr")[1:]:
            cells = [normalize(c.get_text(" ")) for c in row.find_all(["td", "th"])]
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            day = dt.date(year, month, int(cells[0]))
            text = cells[2]
            ranges = find_time_ranges(text)
            note = re.sub(r"\d{1,2}:\d{2}\s*[~〜～]\s*\d{1,2}:\d{2}", "", text).strip(" ※")
            if ranges:
                found[day] = open_day([Session(a, b) for a, b in ranges], url, note=note)
            elif text:
                found[day] = simple_day(CLOSED, url, text)
    last = max(found) if found else None
    out = {}
    for d in date_range(start, end):
        if not in_season(d, (10, 1), (5, 31)):
            out[d] = simple_day(OFF_SEASON, url, "スケートリンクの営業は10月〜5月")
        elif d in found:
            out[d] = found[d]
        elif last and d <= last:
            out[d] = simple_day(CLOSED, url, "一般公開の掲載なし")
        else:
            out[d] = simple_day(UNPUBLISHED, url, "まだ公開されていません")
    return out


# ---------------------------------------------------------------- 明治神宮外苑アイススケート場

def jingu_planned(day, url):
    start = "10:00" if is_weekend_or_holiday(day) else "13:00"
    note = "基本営業時間からの予定"
    if day.month in (1, 2, 3) or (day.month == 12 and day.day >= 25):
        note += "（12月末〜3月末の平日は時間が変わることがあります）"
    return open_day([Session(start, "18:00")], url, basis=PLANNED, note=note, confidence="medium")


def parse_jingu(html: str, start, end, url, today):
    soup = BeautifulSoup(html, "html.parser")
    out = {d: jingu_planned(d, url) for d in date_range(start, end)}
    head = soup.select_one(".schedule__head")
    body = soup.select_one(".schedule__container")
    if head and body and today in out:
        head_text, body_text = normalize(head.get_text(" ")), normalize(body.get_text(" "))
        m = re.search(r"(\d{1,2})月(\d{1,2})日", head_text)
        if m and (int(m.group(1)), int(m.group(2))) == (today.month, today.day):
            ranges = find_time_ranges(body_text)
            if ranges and "一般" in body_text:
                out[today] = open_day([Session(a, b) for a, b in ranges], url)
            elif ranges:
                out[today] = open_day([Session(a, b) for a, b in ranges], url, note=body_text)
            else:
                out[today] = simple_day(CLOSED, url, body_text or "本日の一般営業なし")
    return out


# ---------------------------------------------------------------- 東大和スケートセンター

def parse_higashiyamato(html: str, start, end, url, today):
    soup = BeautifulSoup(html, "html.parser")
    out = {d: simple_day(UNKNOWN, url, "月間カレンダーが画像のため取得準備中") for d in date_range(start, end)}
    texts = [normalize(t.get_text(" ")) for t in soup.select(".comp-icearena-announce__text")]
    joined = " ".join(texts)
    if "本日の営業時間" in joined and today in out:
        ranges = find_time_ranges(joined)
        if ranges and "一般滑走" in joined:
            out[today] = open_day([Session(a, b) for a, b in ranges], url)
        elif "休" in joined:
            out[today] = simple_day(CLOSED, url, joined.replace("本日の営業時間", "").strip())
    return out


# ---------------------------------------------------------------- 取得の入口

def fetch_daido(start, end, url, today):
    return parse_daido(fetch_text("https://www.seibu-leisure.co.jp/icearena/"), start, end, url, today)


def fetch_edogawa(start, end, url, today):
    return parse_edogawa(fetch_text("https://www.edogawa-sportsland.com/"), start, end, url, today)


def fetch_jingu(start, end, url, today):
    return parse_jingu(fetch_text("https://meijijingugaien-iceskating.com/"), start, end, url, today)


def fetch_higashiyamato(start, end, url, today):
    return parse_higashiyamato(fetch_text("https://www.seibu-leisure.co.jp/web/iceskate/index.html"),
                               start, end, url, today)
