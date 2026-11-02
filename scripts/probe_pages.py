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
    "https://www.icespace.co.jp/hpgen/HPB/shop/sitemap.html",
    *[f"https://www.icespace.co.jp/hpgen/HPB/entries/{n}.html" for n in (22, 23, 24, 26, 27, 28)],
    "https://www.icespace.co.jp/pic-labo/MF-2026-10-20.jpg",
    "https://www.icespace.co.jp/pic-labo/llimg/MF-2026-10-C.jpg",
    "https://www.icespace.co.jp/hpgen/HPB/theme/js/cal.js?t=20260301",
]
index = {}
for i, url in enumerate(URLS):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        name = f"{i:02d}_" + re.sub(r"[^\w]+", "_", urllib.parse.urlparse(url).netloc + urllib.parse.urlparse(url).path)[-60:] + (".bin" if url.endswith((".jpg", ".png")) else ".html")
        (OUT / name).write_bytes(body)
        index[url] = name
    except Exception as e:  # noqa: BLE001
        index[url] = f"ERROR {type(e).__name__}: {e}"
(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
