import base64
import json
import os
import time
from pathlib import Path

import requests

try:
    from .env_config import load_env_file
except ImportError:
    from env_config import load_env_file

load_env_file()

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "幕库 Muku")
OPENROUTER_TRANSCRIPTION_MODEL = os.environ.get(
    "OPENROUTER_TRANSCRIPTION_MODEL", "openai/gpt-audio-mini"
)
OPENROUTER_CLEANUP_MODEL = os.environ.get("OPENROUTER_CLEANUP_MODEL", "openai/gpt-4o-mini")
OPENROUTER_ARTICLE_MODEL = os.environ.get("OPENROUTER_ARTICLE_MODEL", "openai/gpt-4o-mini")
OPENROUTER_TIMEOUT_SECONDS = int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "600"))
OPENROUTER_MAX_RETRIES = int(os.environ.get("OPENROUTER_MAX_RETRIES", "3"))


def _safe_header_value(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    try:
        cleaned.encode("latin-1")
        return cleaned
    except UnicodeEncodeError:
        ascii_only = "".join(ch for ch in cleaned if ord(ch) < 128).strip()
        return " ".join(ascii_only.split())


def _headers() -> dict[str, str]:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    if OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL
    if OPENROUTER_APP_NAME:
        safe_app_name = _safe_header_value(OPENROUTER_APP_NAME)
        if safe_app_name:
            headers["X-Title"] = safe_app_name
    return headers


def _post_chat(payload: dict) -> dict:
    url = f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    last_error: Exception | None = None

    for attempt in range(1, OPENROUTER_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=_headers(),
                json=payload,
                timeout=OPENROUTER_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= OPENROUTER_MAX_RETRIES:
                break
            time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError(f"OpenRouter request failed: {last_error}") from last_error


def _encode_audio(audio_path: Path) -> str:
    return base64.b64encode(audio_path.read_bytes()).decode("utf-8")


def _extract_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter response did not contain choices.")

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

    raise RuntimeError("Unable to extract transcript text from OpenRouter response.")


def _ensure_response_not_truncated(data: dict, *, operation: str) -> None:
    choices = data.get("choices") or []
    if not choices:
        return

    choice = choices[0] or {}
    finish_reason = str(choice.get("finish_reason") or choice.get("native_finish_reason") or "").strip().lower()
    if finish_reason != "length":
        return

    raise RuntimeError(
        f"OpenRouter {operation} response was truncated before completion. "
        "Try a shorter clip, prefer direct subtitles, or split the audio before retrying."
    )


def transcribe_audio(audio_path: Path, title: str, source_url: str, language_hint: str) -> dict:
    prompt = (
        "Transcribe this audio faithfully. "
        "Preserve the original language and wording. "
        "Do not summarize. "
        "Return plain text only. "
        "Do not include metadata, titles, source URLs, labels, explanations, or markdown."
    )
    if language_hint and language_hint.lower() != "auto":
        prompt += f" The expected main language is {language_hint}."

    payload = {
        "model": OPENROUTER_TRANSCRIPTION_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": _encode_audio(audio_path),
                            "format": audio_path.suffix.lstrip(".").lower() or "mp3",
                        },
                    },
                ],
            }
        ],
    }

    data = _post_chat(payload)
    _ensure_response_not_truncated(data, operation="transcription")
    return {
        "provider": "openrouter",
        "model": OPENROUTER_TRANSCRIPTION_MODEL,
        "text": _extract_text(data),
        "raw_response": data,
    }


def cleanup_markdown(clean_text: str, title: str, source_url: str) -> dict:
    prompt = (
        "Turn the following transcript into clean Markdown.\n"
        "Requirements:\n"
        "- Keep the original language.\n"
        "- Keep the content faithful.\n"
        "- Add a short summary.\n"
        "- Add concise section headings.\n"
        "- Do not invent facts.\n"
        "- Output Markdown only.\n\n"
        f"Title: {title}\n"
        f"Source URL: {source_url}\n\n"
        f"Transcript:\n{clean_text}"
    )

    payload = {
        "model": OPENROUTER_CLEANUP_MODEL,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    data = _post_chat(payload)
    return {
        "provider": "openrouter",
        "model": OPENROUTER_CLEANUP_MODEL,
        "text": _extract_text(data),
        "raw_response": data,
    }


def generate_article_draft(
    *,
    transcript_text: str,
    system_prompt: str,
    title: str,
    source_url: str,
    platform: str,
    source_author: str | None = None,
) -> dict:
    payload = {
        "model": OPENROUTER_ARTICLE_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "请按 System Prompt 生成中文成稿。\n\n"
                    "【元信息】\n"
                    f"- 标题：{title}\n"
                    f"- 作者：{(source_author or '').strip() or '未知作者'}\n"
                    f"- 平台：{platform}\n"
                    f"- 原始链接：{source_url}\n\n"
                    "【逐字稿全文】\n"
                    f"{transcript_text}"
                ),
            },
        ],
    }

    data = _post_chat(payload)
    return {
        "provider": "openrouter",
        "model": OPENROUTER_ARTICLE_MODEL,
        "text": _extract_text(data),
        "raw_response": data,
    }
