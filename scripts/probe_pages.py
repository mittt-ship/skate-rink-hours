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
    "https://drive.google.com/uc?export=download&id=1PPgfN23lXaU5dBCCaOxi3KcwtdJ57Ops",
]
index = {}
for i, url in enumerate(URLS):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        name = f"{i:02d}_" + re.sub(r"[^\w]+", "_", urllib.parse.urlparse(url).netloc + urllib.parse.urlparse(url).path)[-60:] + (".bin" if url.endswith((".jpg", ".png")) or "drive.google" in url else ".html")
        (OUT / name).write_bytes(body)
        index[url] = name
        # お知らせ記事に貼られた予定表の画像も保存する
        for img in re.findall(r'src="(https://www\.icespace\.co\.jp/pic-labo/[A-Z]{2}-[^"]+)"', body.decode("utf-8", "replace")):
            if img not in URLS:
                URLS.append(img)
    except Exception as e:  # noqa: BLE001
        index[url] = f"ERROR {type(e).__name__}: {e}"
(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
