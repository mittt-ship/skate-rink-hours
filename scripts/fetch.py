"""全施設の一般営業時間を取得して docs/data に保存する（GitHub Actions から1日3回実行）。"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skate import store  # noqa: E402
from skate.common import UNKNOWN, date_range, end_of_next_month, now_jst, simple_day  # noqa: E402
from skate.rinks import RINKS  # noqa: E402
from skate.sources import calendars, html_pages, rules  # noqa: E402


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
        "higashiyamato": lambda url: html_pages.fetch_higashiyamato(today, end, url, today, now.hour),
        "maorink": lambda url: calendars.fetch_maorink(today, end, url),
        "tatsumi": lambda url: calendars.fetch_tatsumi(today, end, url),
        "edogawa": lambda url: html_pages.fetch_edogawa(today, end, url, today),
        "aqua": lambda url: rules.aqua(today, end, url),
        "saitama": lambda url: calendars.fetch_saitama(today, end, url),
        "utsunomiya": lambda url: rules.utsunomiya(today, end, url),
        "kirifuri": lambda url: rules.kirifuri(today, end, url, manual),
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
