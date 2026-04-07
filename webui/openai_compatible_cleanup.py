import json
import os
import time
from pathlib import Path

import requests

from env_config import load_env_file

load_env_file()

AI_CLEANUP_ENABLED = os.environ.get("ENABLE_AI_CLEANUP", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AI_CLEANUP_FALLBACK_LOCAL = os.environ.get(
    "AI_CLEANUP_FALLBACK_LOCAL", "true"
).strip().lower() in {"1", "true", "yes", "on"}
AI_CLEANUP_BASE_URL = os.environ.get(
    "AI_CLEANUP_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"
).rstrip("/")
AI_CLEANUP_API_KEY = os.environ.get("AI_CLEANUP_API_KEY", "").strip()
AI_CLEANUP_MODEL = os.environ.get("AI_CLEANUP_MODEL", "GLM-4.5").strip()
AI_CLEANUP_PROVIDER_LABEL = os.environ.get("AI_CLEANUP_PROVIDER_LABEL", "zhipu-coding").strip()
AI_CLEANUP_PROMPT_FILE = os.environ.get(
    "AI_CLEANUP_PROMPT_FILE",
    str(Path(__file__).resolve().parents[1] / "角色提示词.md"),
).strip()
AI_CLEANUP_TIMEOUT_SECONDS = int(os.environ.get("AI_CLEANUP_TIMEOUT_SECONDS", "300"))
AI_CLEANUP_MAX_RETRIES = int(os.environ.get("AI_CLEANUP_MAX_RETRIES", "2"))


def cleanup_transcript(text: str, title: str, source_url: str) -> dict:
    if not AI_CLEANUP_API_KEY:
        raise RuntimeError("AI_CLEANUP_API_KEY is not configured.")

    payload = build_cleanup_payload(text=text, title=title, source_url=source_url)
    data = _post_chat(payload)
    return {
        "provider": AI_CLEANUP_PROVIDER_LABEL,
        "model": AI_CLEANUP_MODEL,
        "text": _extract_text(data),
        "raw_response": data,
    }


def build_cleanup_payload(*, text: str, title: str, source_url: str) -> dict:
    prompt = _load_system_prompt()
    return {
        "model": AI_CLEANUP_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请严格按照系统角色提示词，对下面的 ASR 文本做清洗。\n\n"
                    f"标题：{title}\n"
                    f"来源：{source_url}\n\n"
                    "原始文本：\n"
                    f"{text}"
                ),
            },
        ],
    }


def _load_system_prompt() -> str:
    prompt_path = Path(AI_CLEANUP_PROMPT_FILE)
    if not prompt_path.exists():
        raise RuntimeError(f"AI cleanup prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8").strip()


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {AI_CLEANUP_API_KEY}",
        "Content-Type": "application/json",
    }


def _post_chat(payload: dict) -> dict:
    url = f"{AI_CLEANUP_BASE_URL}/chat/completions"
    last_error: Exception | None = None

    for attempt in range(1, AI_CLEANUP_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=_headers(),
                json=payload,
                timeout=AI_CLEANUP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= AI_CLEANUP_MAX_RETRIES:
                break
            time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError(f"AI cleanup request failed: {last_error}") from last_error


def _extract_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI cleanup response did not contain choices.")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        if text_parts:
            return "\n".join(text_parts).strip()

    raise RuntimeError("Unable to extract text from AI cleanup response.")
