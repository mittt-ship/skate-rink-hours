"""取得テスト：各スケート場の併設ショップ情報（営業時間・担当者）が公開ページから拾えるか。

本番の更新処理とは無関係。結果は probe_results/ に保存する。
"""

import json
import re
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

OUT = Path("probe_results")
OUT.mkdir(exist_ok=True)
UA = "skate-rink-hours/0.1 (family schedule viewer; github.com/mittt-ship/skate-rink-hours)"

START = {
    "daido": "https://www.seibu-leisure.co.jp/icearena/",
    "higashiyamato": "https://www.seibu-leisure.co.jp/web/iceskate/index.html",
    "saitama": "http://www.saitama-icearena.com/",
    "aqua": "http://www.aquarink-chiba.jp/",
    "icespace": "https://www.icespace.co.jp/",
    "edogawa": "https://www.edogawa-sportsland.com/",
    "kosesp": "https://www.kose-sp.pref.yamanashi.jp/info/use/216606/",
    "kosugi_osaka_tempo": "https://kosugi-skate.o.oo7.jp/tempo.html",
    "kosugi_com_company": "https://www.kosugi-skate.com/html/company.html",
    "jingu": "https://meijijingugaien-iceskating.com/",
    "west": "https://www.skateshopwest.jp/",
    "yokohama_about": "https://yokohama-icearena.jp/about/",
}
FOLLOW = re.compile(r"施設|ショップ|SHOP|shop|研磨|フロア|館内|設備|facility|guide|店舗|営業|お知らせ|news", re.I)
KEY = re.compile(r"ショップ|SHOP|Shop|研磨|小杉|アイススペース|ウエスト|プロショップ|担当|出勤|スタッフ")


def fetch(url):
    url = urllib.parse.quote(url, safe=":/?&=%#~+,;@!$'()*")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            pass
    return body.decode("utf-8", "replace")


def text_of(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", t)))


def snippets(text):
    out = []
    for m in KEY.finditer(text):
        s = text[max(0, m.start() - 80): m.end() + 160].strip()
        if not any(s[:60] in o for o in out):
            out.append(s)
    return out[:15]


report = {}
for name, start in START.items():
    entry = {"start": start, "pages": []}
    try:
        html = fetch(start)
    except Exception as e:  # noqa: BLE001
        entry["error"] = f"{type(e).__name__}: {e}"
        report[name] = entry
        continue
    pages = [(start, html)]
    host = urllib.parse.urlparse(start).netloc
    links = []
    for href, label in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, flags=re.S | re.I):
        u = urllib.parse.urljoin(start, unescape(href))
        lab = text_of(label)
        if urllib.parse.urlparse(u).netloc == host and (FOLLOW.search(lab) or FOLLOW.search(u)) and u != start:
            if u not in links and not u.lower().endswith((".pdf", ".jpg", ".png")):
                links.append(u)
    entry["candidate_links"] = links[:30]
    for u in links[:8]:
        try:
            pages.append((u, fetch(u)))
        except Exception as e:  # noqa: BLE001
            entry["pages"].append({"url": u, "error": str(e)})
    for u, h in pages:
        sn = snippets(text_of(h))
        sns = sorted(set(re.findall(r"https?://(?:www\.)?(?:instagram\.com|x\.com|twitter\.com|calendar\.google\.com)/[^\"'\s<>]+", h)))[:8]
        entry["pages"].append({"url": u, "snippets": sn, "sns_or_calendar": sns})
    report[name] = entry
    print(name, "ok", len(pages))

(OUT / "shops.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
