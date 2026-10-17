"""月ごとのJSONファイルへの保存。

- docs/data/days/YYYY-MM.json : {"month": "YYYY-MM", "days": {"YYYY-MM-DD": {施設ID: レコード}}}
- docs/data/meta.json          : 施設一覧、最終取得時刻、各施設の取得状況、保存している月
今日以降の日付は毎回上書きし、過去の日付はそのまま残す（その日の最後の取得結果が確定版になる）。
14か月より古い月のファイルは削除する。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

DATA_DIR = Path("docs/data")
DAYS_DIR = DATA_DIR / "days"
KEEP_MONTHS = 14


def _month_key(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _dump(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def save_days(records_by_rink: dict, today: dt.date):
    """records_by_rink: {施設ID: {日付: レコード(dict)}}"""
    by_month: dict[str, dict] = {}
    for rink_id, days in records_by_rink.items():
        for day, record in days.items():
            if day < today:
                continue
            by_month.setdefault(_month_key(day), {}).setdefault(day.isoformat(), {})[rink_id] = record
    for month, days in by_month.items():
        path = DAYS_DIR / f"{month}.json"
        data = _load(path) or {"month": month, "days": {}}
        for iso, rinks in days.items():
            data["days"].setdefault(iso, {}).update(rinks)
        _dump(path, data)


def prune(today: dt.date) -> list[str]:
    y, m = today.year, today.month - KEEP_MONTHS
    while m <= 0:
        y, m = y - 1, m + 12
    oldest = f"{y:04d}-{m:02d}"
    kept = []
    for path in sorted(DAYS_DIR.glob("*.json")):
        if path.stem < oldest:
            path.unlink()
        else:
            kept.append(path.stem)
    return kept


def existing_future(rink_id: str, start: dt.date, end: dt.date) -> dict:
    """取得に失敗した施設のために、保存済みのデータを読み出す。"""
    out = {}
    for path in DAYS_DIR.glob("*.json"):
        for iso, rinks in _load(path).get("days", {}).items():
            day = dt.date.fromisoformat(iso)
            if start <= day <= end and rink_id in rinks:
                out[day] = rinks[rink_id]
    return out


def save_meta(meta: dict):
    _dump(DATA_DIR / "meta.json", meta)


def load_meta() -> dict:
    return _load(DATA_DIR / "meta.json")
