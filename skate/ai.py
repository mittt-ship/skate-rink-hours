"""AI（Claude API）でPDF・画像・お知らせ文を読む。

同じ内容のファイルを何度も読ませないよう、内容のハッシュをキーに結果を保存する
（docs/data/ai_cache/）。中身が変わったときだけAPIを呼ぶので、費用はごく少額に収まる。
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
CACHE_DIR = Path("docs/data/ai_cache")
CACHE_KEEP_DAYS = 60
PROMPT_VERSION = "v1"


class AIError(RuntimeError):
    pass


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _key(rink_id: str, payload: bytes, prompt: str) -> str:
    h = hashlib.sha256(payload + prompt.encode() + PROMPT_VERSION.encode()).hexdigest()[:20]
    return f"{rink_id}-{h}"


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise AIError("AIの返答にJSONが見つかりません")
    return json.loads(text[start:end + 1])


def _call(content: list, max_tokens: int = 8000) -> tuple[dict, dict]:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise AIError("APIキー（ANTHROPIC_API_KEY）が設定されていません")
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        raise AIError(f"API HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from e
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if data.get("stop_reason") == "max_tokens" and not text.strip().endswith("}"):
        raise AIError("AIの返答が長さの上限で途中で切れました")
    return _extract_json(text), data.get("usage", {})


def read(rink_id: str, payload: bytes, media_type: str, prompt: str, today: dt.date) -> dict:
    """payload（PDF・画像・テキスト）をAIに読ませ、JSONを返す。キャッシュがあればそれを使う。"""
    key = _key(rink_id, payload, prompt)
    path = _cache_path(key)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("used_on") != today.isoformat():
            cached["used_on"] = today.isoformat()
            path.write_text(json.dumps(cached, ensure_ascii=False, indent=1), encoding="utf-8")
        return cached["result"]

    if media_type == "application/pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": media_type,
                                                "data": base64.b64encode(payload).decode()}}
    elif media_type.startswith("image/"):
        block = {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.b64encode(payload).decode()}}
    else:
        block = {"type": "text", "text": payload.decode("utf-8", "replace")}
    result, usage = _call([block, {"type": "text", "text": prompt}])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "rink_id": rink_id, "created_on": today.isoformat(), "used_on": today.isoformat(),
        "model": MODEL, "usage": usage, "result": result,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"     AI読み取り {rink_id}: 入力 {usage.get('input_tokens')} / 出力 {usage.get('output_tokens')} トークン")
    return result


def prune_cache(today: dt.date):
    if not CACHE_DIR.exists():
        return
    limit = (today - dt.timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    for path in CACHE_DIR.glob("*.json"):
        try:
            used = json.loads(path.read_text(encoding="utf-8")).get("used_on", "")
        except ValueError:
            used = ""
        if used < limit:
            path.unlink()
