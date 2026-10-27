"""`command:` backend for OpenAI-compatible chat APIs (the second model family for inversion).

Reads {"system","user","model"} JSON on stdin; prints {"text","input_tokens","output_tokens","cost_usd"}.
Environment: OPENAI_API_KEY; OPENAI_REVIEW_MODEL (or --model); optional OPENAI_BASE_URL.
Cost is reported as 0 because prices are not hard-coded; token counts are returned instead."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def call(system: str, user: str, model: str, key: str, base: str, timeout: int = 600) -> dict:
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": system},
                                                     {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    usage = data.get("usage", {})
    return {"text": data["choices"][0]["message"]["content"] or "",
            "input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0),
            "cost_usd": 0.0}


def main() -> int:
    req = json.load(sys.stdin)
    key = os.environ.get("OPENAI_API_KEY")
    model = req.get("model") or os.environ.get("OPENAI_REVIEW_MODEL")
    if not key:
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 2
    if not model:
        print("no model: pass --model or set OPENAI_REVIEW_MODEL", file=sys.stderr)
        return 2
    try:
        out = call(req["system"], req["user"], model, key, os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
