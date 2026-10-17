"""全施設の一般営業時間を取得して docs/data に保存する（GitHub Actions から1日3回実行）。"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datetime as dt  # noqa: E402

from skate import ai, store  # noqa: E402
from skate.common import UNKNOWN, date_range, end_of_next_month, in_season, now_jst, simple_day  # noqa: E402
from skate.rinks import RINK_BY_ID, RINKS  # noqa: E402
from skate.sources import calendars, documents, html_pages, rules  # noqa: E402

warnings: dict[str, str] = {}


def with_news(rid, planned, today, end):
    """基本営業時間の予定に、お知らせ欄の変更点を重ねる。AIが失敗しても予定は表示する。"""
    try:
        return documents.apply_news_exceptions(RINK_BY_ID[rid], planned, today, end)
    except Exception as e:  # noqa: BLE001
        warnings[rid] = f"お知らせ欄の読み取りに失敗：{type(e).__name__}: {e}"
        print(f"WARN {rid}: {warnings[rid]}")
        return planned


def higashiyamato(today, end, url, hour):
    days = documents.fetch_monthly(RINK_BY_ID["higashiyamato"], today, end, today)
    today_rec = html_pages.fetch_higashiyamato(today, end, url, today, hour).get(today)
    if today_rec and today_rec.status != UNKNOWN:
        days[today] = today_rec  # 当日はページの「本日の営業時間」を優先
    return days


def main():
    now = now_jst()
    today = now.date()
    end = end_of_next_month(today)
    fetched_at = now.isoformat()
    sheet_url = os.environ.get("MANUAL_SHEET_CSV_URL", "")

    try:
        manual = rules.fetch_manual_sheet(sheet_url)
        manual_error = None
    except Exception as e:  # noqa: BLE001
        manual, manual_error = {}, f"{type(e).__name__}: {e}"

    sources = {
        "jingu": lambda url: html_pages.fetch_jingu(today, end, url, today),
        "daido": lambda url: html_pages.fetch_daido(today, end, url, today),
        "higashiyamato": lambda url: higashiyamato(today, end, url, now.hour),
        "maorink": lambda url: calendars.fetch_maorink(today, end, url),
        "tatsumi": lambda url: calendars.fetch_tatsumi(today, end, url),
        "edogawa": lambda url: html_pages.fetch_edogawa(today, end, url, today),
        "mfice": lambda url: documents.fetch_monthly(RINK_BY_ID["mfice"], today, end, today),
        "aqua": lambda url: with_news("aqua", rules.aqua(today, end, url), today, end),
        "shinyoko": lambda url: documents.fetch_monthly(RINK_BY_ID["shinyoko"], today, end, today),
        "yokohama": lambda url: documents.fetch_monthly(RINK_BY_ID["yokohama"], today, end, today),
        "ginga": lambda url: documents.fetch_monthly(
            RINK_BY_ID["ginga"], today, end, today,
            season=lambda d: dt.date(2026, 10, 20) <= d <= dt.date(2027, 3, 31)),
        "saitama": lambda url: calendars.fetch_saitama(today, end, url),
        "utsunomiya": lambda url: with_news("utsunomiya", rules.utsunomiya(today, end, url), today, end),
        "kirifuri": lambda url: rules.kirifuri(today, end, url, manual),
        "kosesp": lambda url: documents.fetch_monthly(
            RINK_BY_ID["kosesp"], today, end, today, season=lambda d: in_season(d, (7, 1), (3, 31))),
    }

    old_meta = {r["id"]: r for r in store.load_meta().get("rinks", [])}
    records, rink_meta = {}, []
    for rink in RINKS:
        rid, url = rink["id"], rink["schedule_url"]
        info = dict(rink)
        info["last_success"] = old_meta.get(rid, {}).get("last_success")
        info["last_error"] = None
        try:
            if rid in sources:
                days = sources[rid](url)
            else:
                days = rules.pending(rid, today, end, url)
            records[rid] = {d: rec.to_json(fetched_at) for d, rec in days.items()}
            info["last_success"] = fetched_at
            if rid == "kirifuri" and manual_error:
                info["last_error"] = f"手入力シートの取得に失敗：{manual_error}"
            if rid in warnings:
                info["last_error"] = warnings[rid]
            print(f"OK   {rid}: {len(days)} 日分")
        except Exception as e:  # noqa: BLE001
            info["last_error"] = f"{type(e).__name__}: {e}"
            print(f"FAIL {rid}: {info['last_error']}")
            traceback.print_exc()
            kept = store.existing_future(rid, today, end)
            records[rid] = {
                d: simple_day(UNKNOWN, url, "取得エラーのため情報を更新できませんでした").to_json(fetched_at)
                for d in date_range(today, end) if d not in kept
            }
        rink_meta.append(info)

    store.save_days(records, today)
    months = store.prune(today)
    ai.prune_cache(today)
    store.save_meta({
        "generated_at": fetched_at,
        "today": today.isoformat(),
        "range_end": end.isoformat(),
        "months": months,
        "rinks": rink_meta,
    })
    failed = [r["id"] for r in rink_meta if r["last_error"]]
    print(f"完了：{len(RINKS)} 施設、エラー {len(failed)} 件 {failed}")


if __name__ == "__main__":
    main()
