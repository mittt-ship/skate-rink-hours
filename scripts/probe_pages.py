"""取得テスト：指定したページの中身（HTML・画像の一覧）をそのまま保存する。本番処理とは無関係。"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("probe_results/pages2")
OUT.mkdir(parents=True, exist_ok=True)
UA = "skate-rink-hours/0.1 (family schedule viewer; github.com/mittt-ship/skate-rink-hours)"
URLS = [
    "https://www.icespace.co.jp/",
    *[f"https://www.icespace.co.jp/hpgen/HPB/entries/{n}.html" for n in (2, 5, 6, 12, 14, 19, 21, 25, 29, 30, 31, 32, 33)],
    "http://www.saitama-icearena.com/shop/zam/index.htm",
    "http://www.saitama-icearena.com/facility.html",
    "https://www.seibu-leisure.co.jp/icearena/floormap/index.html",
    "https://www.seibu-leisure.co.jp/web/51078/index.html",
    "http://www.aquarink-chiba.jp/outline.html",
    "https://www.edogawa-sportsland.com/other/",
    "https://www.kose-sp.pref.yamanashi.jp/guide/957/",
]
index = {}
for i, url in enumerate(URLS):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        name = f"{i:02d}_" + re.sub(r"[^\w]+", "_", urllib.parse.urlparse(url).netloc + urllib.parse.urlparse(url).path)[-60:] + ".html"
        (OUT / name).write_bytes(body)
        index[url] = name
    except Exception as e:  # noqa: BLE001
        index[url] = f"ERROR {type(e).__name__}: {e}"
(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
