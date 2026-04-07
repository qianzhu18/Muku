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


def _default_prompt_path(filename: str) -> str:
    package_root = Path(__file__).resolve().parent
    candidates = [
        package_root.parent / filename,
        package_root / "prompts" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[-1])

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
    _default_prompt_path("角色提示词.md"),
).strip()

ENABLE_ARTICLE_DRAFT = os.environ.get("ENABLE_ARTICLE_DRAFT", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ARTICLE_DRAFT_BASE_URL = os.environ.get("ARTICLE_DRAFT_BASE_URL", AI_CLEANUP_BASE_URL).rstrip("/")
ARTICLE_DRAFT_API_KEY = os.environ.get("ARTICLE_DRAFT_API_KEY", AI_CLEANUP_API_KEY).strip()
ARTICLE_DRAFT_MODEL = os.environ.get("ARTICLE_DRAFT_MODEL", AI_CLEANUP_MODEL).strip()
ARTICLE_DRAFT_PROVIDER_LABEL = os.environ.get(
    "ARTICLE_DRAFT_PROVIDER_LABEL", AI_CLEANUP_PROVIDER_LABEL
).strip()
ARTICLE_DRAFT_PROMPT_FILE = os.environ.get(
    "ARTICLE_DRAFT_PROMPT_FILE",
    _default_prompt_path("解析提示词.md"),
).strip()

AI_TEXT_TIMEOUT_SECONDS = int(os.environ.get("AI_TEXT_TIMEOUT_SECONDS", "300"))
AI_TEXT_MAX_RETRIES = int(os.environ.get("AI_TEXT_MAX_RETRIES", "2"))


def cleanup_transcript(text: str, title: str, source_url: str) -> dict:
    if not AI_CLEANUP_API_KEY:
        raise RuntimeError("AI_CLEANUP_API_KEY is not configured.")

    payload = build_cleanup_payload(text=text, title=title, source_url=source_url)
    data = _post_chat(
        base_url=AI_CLEANUP_BASE_URL,
        api_key=AI_CLEANUP_API_KEY,
        payload=payload,
    )
    return {
        "provider": AI_CLEANUP_PROVIDER_LABEL,
        "model": AI_CLEANUP_MODEL,
        "text": _extract_text(data),
        "raw_response": data,
    }


def generate_article_draft(
    *,
    text: str,
    title: str,
    source_url: str,
    platform: str,
) -> dict:
    if not ARTICLE_DRAFT_API_KEY:
        raise RuntimeError("ARTICLE_DRAFT_API_KEY is not configured.")

    payload = build_article_payload(
        text=text,
        title=title,
        source_url=source_url,
        platform=platform,
    )
    data = _post_chat(
        base_url=ARTICLE_DRAFT_BASE_URL,
        api_key=ARTICLE_DRAFT_API_KEY,
        payload=payload,
    )
    return {
        "provider": ARTICLE_DRAFT_PROVIDER_LABEL,
        "model": ARTICLE_DRAFT_MODEL,
        "text": _extract_text(data),
        "raw_response": data,
    }


def build_cleanup_payload(*, text: str, title: str, source_url: str) -> dict:
    prompt = _load_prompt(AI_CLEANUP_PROMPT_FILE, "AI cleanup prompt")
    return {
        "model": AI_CLEANUP_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请严格按照系统角色提示词，对下面的 ASR 文本做清洗。\n"
                    "只输出清洗后的正文，如有必要再附上修改说明。\n"
                    "不要输出标题、来源、前言、markdown frontmatter、标签或解释。\n\n"
                    f"标题：{title}\n"
                    f"来源：{source_url}\n\n"
                    "原始文本：\n"
                    f"{text}"
                ),
            },
        ],
    }


def build_article_payload(
    *,
    text: str,
    title: str,
    source_url: str,
    platform: str,
) -> dict:
    prompt = _load_prompt(ARTICLE_DRAFT_PROMPT_FILE, "Article draft prompt")
    return {
        "model": ARTICLE_DRAFT_MODEL,
        "temperature": 0.35,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请按 System Prompt 生成中文成稿。\n\n"
                    "【元信息】\n"
                    f"- 标题：{title}\n"
                    f"- 平台：{platform}\n"
                    f"- 原始链接：{source_url}\n\n"
                    "【逐字稿全文】\n"
                    f"{text}"
                ),
            },
        ],
    }


def _load_prompt(prompt_path_str: str, prompt_label: str) -> str:
    prompt_path = Path(prompt_path_str)
    if not prompt_path.exists():
        raise RuntimeError(f"{prompt_label} file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8").strip()


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _post_chat(*, base_url: str, api_key: str, payload: dict) -> dict:
    url = f"{base_url}/chat/completions"
    last_error: Exception | None = None

    for attempt in range(1, AI_TEXT_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=_headers(api_key),
                json=payload,
                timeout=AI_TEXT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= AI_TEXT_MAX_RETRIES:
                break
            time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError(f"AI text request failed: {last_error}") from last_error


def _extract_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI text response did not contain choices.")

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

    raise RuntimeError("Unable to extract text from AI text response.")
