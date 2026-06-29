import json
import os
import random
import time
from dataclasses import dataclass, replace
from pathlib import Path

import requests

try:
    from .env_config import load_env_file
except ImportError:
    from env_config import load_env_file

try:
    from .http_utils import request_kwargs
except ImportError:
    from http_utils import request_kwargs

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


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def normalize_text_backend_model(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    alias_map = {
        "mimo-v2.5": "mimo-v2.5",
        "mimo v2.5": "mimo-v2.5",
        "mimo-v2.5-pro": "mimo-v2.5-pro",
        "mimo v2.5 pro": "mimo-v2.5-pro",
    }
    return alias_map.get(normalized.lower(), normalized)


def _dedupe_models(models: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for model in models:
        normalized = normalize_text_backend_model(model)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _env_csv(name: str) -> tuple[str, ...]:
    value = os.environ.get(name)
    if value is None:
        return ()
    return _dedupe_models(tuple(part.strip() for part in value.split(",")))


def _default_fallback_models(base_url: str, model: str) -> tuple[str, ...]:
    normalized_base_url = (base_url or "").lower()
    if "xiaomimimo.com" not in normalized_base_url:
        return ()
    ladder = ("mimo-v2.5", "mimo-v2.5-pro")
    primary = normalize_text_backend_model(model)
    return tuple(candidate for candidate in ladder if candidate != primary)


DEFAULT_AI_TEXT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_AI_TEXT_MODEL = "stepfun/step-3.7-flash"
DEFAULT_AI_TEXT_PROVIDER_LABEL = "openrouter"

AI_CLEANUP_ENABLED = _env_bool("ENABLE_AI_CLEANUP", True)
AI_CLEANUP_FALLBACK_LOCAL = _env_bool("AI_CLEANUP_FALLBACK_LOCAL", True)
AI_CLEANUP_BASE_URL = os.environ.get(
    "AI_CLEANUP_BASE_URL", DEFAULT_AI_TEXT_BASE_URL
).rstrip("/")
AI_CLEANUP_API_KEY = os.environ.get("AI_CLEANUP_API_KEY", "").strip()
AI_CLEANUP_MODEL = normalize_text_backend_model(
    os.environ.get("AI_CLEANUP_MODEL", DEFAULT_AI_TEXT_MODEL).strip()
)
AI_CLEANUP_PROVIDER_LABEL = os.environ.get(
    "AI_CLEANUP_PROVIDER_LABEL", DEFAULT_AI_TEXT_PROVIDER_LABEL
).strip()
AI_CLEANUP_FALLBACK_MODELS = _env_csv("AI_CLEANUP_FALLBACK_MODELS")
AI_CLEANUP_PROMPT_FILE = os.environ.get(
    "AI_CLEANUP_PROMPT_FILE",
    _default_prompt_path("角色提示词.md"),
).strip()
AI_CLEANUP_PROMPT_TEXT = os.environ.get("AI_CLEANUP_PROMPT_TEXT", "")

ENABLE_ARTICLE_DRAFT = _env_bool("ENABLE_ARTICLE_DRAFT", True)
ARTICLE_DRAFT_BASE_URL = os.environ.get("ARTICLE_DRAFT_BASE_URL", AI_CLEANUP_BASE_URL).rstrip("/")
ARTICLE_DRAFT_API_KEY = os.environ.get("ARTICLE_DRAFT_API_KEY", AI_CLEANUP_API_KEY).strip()
ARTICLE_DRAFT_MODEL = normalize_text_backend_model(
    os.environ.get("ARTICLE_DRAFT_MODEL", AI_CLEANUP_MODEL).strip()
)
ARTICLE_DRAFT_PROVIDER_LABEL = os.environ.get(
    "ARTICLE_DRAFT_PROVIDER_LABEL", AI_CLEANUP_PROVIDER_LABEL
).strip()
ARTICLE_DRAFT_FALLBACK_MODELS = _env_csv("ARTICLE_DRAFT_FALLBACK_MODELS")
ARTICLE_DRAFT_PROMPT_FILE = os.environ.get(
    "ARTICLE_DRAFT_PROMPT_FILE",
    _default_prompt_path("解析提示词.md"),
).strip()
ARTICLE_DRAFT_PROMPT_TEXT = os.environ.get("ARTICLE_DRAFT_PROMPT_TEXT", "")

ENABLE_KNOWLEDGE_DRAFT = _env_bool("ENABLE_KNOWLEDGE_DRAFT", True)
KNOWLEDGE_DRAFT_BASE_URL = os.environ.get("KNOWLEDGE_DRAFT_BASE_URL", ARTICLE_DRAFT_BASE_URL).rstrip("/")
KNOWLEDGE_DRAFT_API_KEY = os.environ.get("KNOWLEDGE_DRAFT_API_KEY", ARTICLE_DRAFT_API_KEY).strip()
KNOWLEDGE_DRAFT_MODEL = normalize_text_backend_model(
    os.environ.get("KNOWLEDGE_DRAFT_MODEL", ARTICLE_DRAFT_MODEL).strip()
)
KNOWLEDGE_DRAFT_PROVIDER_LABEL = os.environ.get(
    "KNOWLEDGE_DRAFT_PROVIDER_LABEL", ARTICLE_DRAFT_PROVIDER_LABEL
).strip()
KNOWLEDGE_DRAFT_FALLBACK_MODELS = _env_csv("KNOWLEDGE_DRAFT_FALLBACK_MODELS")
KNOWLEDGE_DRAFT_PROMPT_FILE = os.environ.get(
    "KNOWLEDGE_DRAFT_PROMPT_FILE",
    _default_prompt_path("知识库提示词.md"),
).strip()
KNOWLEDGE_DRAFT_PROMPT_TEXT = os.environ.get("KNOWLEDGE_DRAFT_PROMPT_TEXT", "")

AI_TEXT_TIMEOUT_SECONDS = _env_int("AI_TEXT_TIMEOUT_SECONDS", 180)
AI_TEXT_CONNECT_TIMEOUT_SECONDS = _env_int("AI_TEXT_CONNECT_TIMEOUT_SECONDS", 20)
AI_TEXT_RETRY_BACKOFF_MAX = _env_int("AI_TEXT_RETRY_BACKOFF_MAX", 60)
AI_TEXT_MAX_RETRIES = _env_int("AI_TEXT_MAX_RETRIES", 4)
AI_CLEANUP_TIMEOUT_SECONDS = _env_int("AI_CLEANUP_TIMEOUT_SECONDS", AI_TEXT_TIMEOUT_SECONDS)
AI_CLEANUP_MAX_RETRIES = _env_int("AI_CLEANUP_MAX_RETRIES", AI_TEXT_MAX_RETRIES)
ARTICLE_DRAFT_TIMEOUT_SECONDS = _env_int("ARTICLE_DRAFT_TIMEOUT_SECONDS", AI_TEXT_TIMEOUT_SECONDS)
ARTICLE_DRAFT_MAX_RETRIES = _env_int("ARTICLE_DRAFT_MAX_RETRIES", AI_TEXT_MAX_RETRIES)
KNOWLEDGE_DRAFT_TIMEOUT_SECONDS = _env_int("KNOWLEDGE_DRAFT_TIMEOUT_SECONDS", ARTICLE_DRAFT_TIMEOUT_SECONDS)
KNOWLEDGE_DRAFT_MAX_RETRIES = _env_int("KNOWLEDGE_DRAFT_MAX_RETRIES", ARTICLE_DRAFT_MAX_RETRIES)


@dataclass(frozen=True)
class TextBackendConfig:
    stage_key: str
    stage_label: str
    base_url: str
    api_key: str
    model: str
    provider_label: str
    timeout_seconds: int
    max_retries: int
    fallback_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatCompletionResult:
    data: dict
    model: str


class AITextRequestError(RuntimeError):
    def __init__(self, config: TextBackendConfig, *, attempts: int, last_error: Exception) -> None:
        self.config = config
        self.attempts = attempts
        self.last_error = last_error
        self.status_code = getattr(getattr(last_error, "response", None), "status_code", None)
        super().__init__(self._build_message())

    @property
    def is_timeout(self) -> bool:
        return isinstance(self.last_error, requests.Timeout)

    def summary(self) -> str:
        if self.is_timeout:
            return f"timed out after {self.attempts} attempts"
        if self.status_code is not None:
            return f"failed with HTTP {self.status_code} after {self.attempts} attempts"
        if isinstance(self.last_error, json.JSONDecodeError):
            return f"returned invalid JSON after {self.attempts} attempts"
        return f"failed after {self.attempts} attempts"

    def fallback_status(self, fallback_label: str) -> str:
        return f"{self.config.stage_label} {self.summary()}. Falling back to {fallback_label}..."

    def _build_message(self) -> str:
        detail = str(self.last_error).strip() or self.last_error.__class__.__name__
        return (
            f"{self.config.stage_label} request {self.summary()} "
            f"(timeout={self.config.timeout_seconds}s, model={self.config.model}, base_url={self.config.base_url}): "
            f"{detail}"
        )


def _stage_config(stage_key: str) -> TextBackendConfig:
    if stage_key == "cleanup":
        return TextBackendConfig(
            stage_key="cleanup",
            stage_label="AI cleanup",
            base_url=AI_CLEANUP_BASE_URL,
            api_key=AI_CLEANUP_API_KEY,
            model=AI_CLEANUP_MODEL,
            provider_label=AI_CLEANUP_PROVIDER_LABEL,
            timeout_seconds=AI_CLEANUP_TIMEOUT_SECONDS,
            max_retries=AI_CLEANUP_MAX_RETRIES,
            fallback_models=AI_CLEANUP_FALLBACK_MODELS or _default_fallback_models(
                AI_CLEANUP_BASE_URL,
                AI_CLEANUP_MODEL,
            ),
        )
    if stage_key == "article":
        return TextBackendConfig(
            stage_key="article",
            stage_label="Article draft",
            base_url=ARTICLE_DRAFT_BASE_URL,
            api_key=ARTICLE_DRAFT_API_KEY,
            model=ARTICLE_DRAFT_MODEL,
            provider_label=ARTICLE_DRAFT_PROVIDER_LABEL,
            timeout_seconds=ARTICLE_DRAFT_TIMEOUT_SECONDS,
            max_retries=ARTICLE_DRAFT_MAX_RETRIES,
            fallback_models=ARTICLE_DRAFT_FALLBACK_MODELS or _default_fallback_models(
                ARTICLE_DRAFT_BASE_URL,
                ARTICLE_DRAFT_MODEL,
            ),
        )
    if stage_key == "knowledge":
        return TextBackendConfig(
            stage_key="knowledge",
            stage_label="Knowledge draft",
            base_url=KNOWLEDGE_DRAFT_BASE_URL,
            api_key=KNOWLEDGE_DRAFT_API_KEY,
            model=KNOWLEDGE_DRAFT_MODEL,
            provider_label=KNOWLEDGE_DRAFT_PROVIDER_LABEL,
            timeout_seconds=KNOWLEDGE_DRAFT_TIMEOUT_SECONDS,
            max_retries=KNOWLEDGE_DRAFT_MAX_RETRIES,
            fallback_models=KNOWLEDGE_DRAFT_FALLBACK_MODELS or _default_fallback_models(
                KNOWLEDGE_DRAFT_BASE_URL,
                KNOWLEDGE_DRAFT_MODEL,
            ),
        )
    raise ValueError(f"Unsupported text backend stage: {stage_key}")


def request_settings_for_stage(stage_key: str) -> dict[str, object]:
    config = _stage_config(stage_key)
    return {
        "stage": config.stage_key,
        "stage_label": config.stage_label,
        "base_url": config.base_url,
        "model": normalize_text_backend_model(config.model),
        "provider_label": config.provider_label,
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "fallback_models": list(config.fallback_models),
    }


def cleanup_transcript(text: str, title: str, source_url: str) -> dict:
    config = _stage_config("cleanup")
    if not config.api_key:
        raise RuntimeError("AI_CLEANUP_API_KEY is not configured.")

    payload = build_cleanup_payload(text=text, title=title, source_url=source_url)
    result = _post_chat(config=config, payload=payload)
    return {
        "provider": config.provider_label,
        "model": result.model,
        "text": _extract_text(result.data),
        "raw_response": result.data,
        "request_config": {
            **request_settings_for_stage("cleanup"),
            "resolved_model": result.model,
        },
    }


def generate_article_draft(
    *,
    text: str,
    title: str,
    source_url: str,
    platform: str,
    source_author: str | None = None,
) -> dict:
    config = _stage_config("article")
    if not config.api_key:
        raise RuntimeError("ARTICLE_DRAFT_API_KEY is not configured.")

    payload = build_article_payload(
        text=text,
        title=title,
        source_url=source_url,
        platform=platform,
        source_author=source_author,
    )
    result = _post_chat(config=config, payload=payload)
    return {
        "provider": config.provider_label,
        "model": result.model,
        "text": _extract_text(result.data),
        "raw_response": result.data,
        "request_config": {
            **request_settings_for_stage("article"),
            "resolved_model": result.model,
        },
    }


def generate_knowledge_draft(
    *,
    text: str,
    title: str,
    source_url: str,
    platform: str,
) -> dict:
    config = _stage_config("knowledge")
    if not config.api_key:
        raise RuntimeError("KNOWLEDGE_DRAFT_API_KEY is not configured.")

    payload = build_knowledge_payload(
        text=text,
        title=title,
        source_url=source_url,
        platform=platform,
    )
    result = _post_chat(config=config, payload=payload)
    return {
        "provider": config.provider_label,
        "model": result.model,
        "text": _extract_text(result.data),
        "raw_response": result.data,
        "request_config": {
            **request_settings_for_stage("knowledge"),
            "resolved_model": result.model,
        },
    }


def build_cleanup_payload(*, text: str, title: str, source_url: str) -> dict:
    prompt = _load_prompt(
        AI_CLEANUP_PROMPT_FILE,
        "AI cleanup prompt",
        inline_text=AI_CLEANUP_PROMPT_TEXT,
    )
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
    source_author: str | None = None,
) -> dict:
    prompt = _load_prompt(
        ARTICLE_DRAFT_PROMPT_FILE,
        "Article draft prompt",
        inline_text=ARTICLE_DRAFT_PROMPT_TEXT,
    )
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
                    f"- 作者：{(source_author or '').strip() or '未知作者'}\n"
                    f"- 平台：{platform}\n"
                    f"- 原始链接：{source_url}\n\n"
                    "【逐字稿全文】\n"
                    f"{text}"
                ),
            },
        ],
    }


def build_knowledge_payload(
    *,
    text: str,
    title: str,
    source_url: str,
    platform: str,
) -> dict:
    prompt = _load_prompt(
        KNOWLEDGE_DRAFT_PROMPT_FILE,
        "Knowledge draft prompt",
        inline_text=KNOWLEDGE_DRAFT_PROMPT_TEXT,
    )
    return {
        "model": KNOWLEDGE_DRAFT_MODEL,
        "temperature": 0.25,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请基于下面的视频逐字稿资产，整理成面向知识库沉淀的中文笔记。\n\n"
                    "【元信息】\n"
                    f"- 标题：{title}\n"
                    f"- 平台：{platform}\n"
                    f"- 原始链接：{source_url}\n\n"
                    "【逐字稿资产】\n"
                    f"{text}"
                ),
            },
        ],
    }


def _load_prompt(prompt_path_str: str, prompt_label: str, *, inline_text: str = "") -> str:
    if inline_text.strip():
        return inline_text.strip()
    prompt_path = Path(prompt_path_str)
    if not prompt_path.exists():
        raise RuntimeError(f"{prompt_label} file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8").strip()


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _should_try_next_model(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if response is None or getattr(response, "status_code", None) != 400:
        return False
    body = str(getattr(response, "text", "") or "").lower()
    return "not supported model" in body or "unsupported model" in body


def _candidate_models(config: TextBackendConfig) -> tuple[str, ...]:
    primary = normalize_text_backend_model(config.model)
    return _dedupe_models((primary, *config.fallback_models))


def _post_chat(*, config: TextBackendConfig, payload: dict) -> ChatCompletionResult:
    url = f"{config.base_url}/chat/completions"
    last_error: Exception | None = None
    attempts = 0
    attempted_model = normalize_text_backend_model(config.model)

    for candidate_model in _candidate_models(config):
        attempted_model = candidate_model
        request_payload = dict(payload)
        request_payload["model"] = candidate_model
        advance_model = False

        for attempt in range(1, config.max_retries + 1):
            attempts += 1
            try:
                response = requests.post(
                    url,
                    headers=_headers(config.api_key),
                    json=request_payload,
                    timeout=(AI_TEXT_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
                    **request_kwargs(),
                )
                response.raise_for_status()
                data = response.json()
                resolved_model = normalize_text_backend_model(str(data.get("model") or candidate_model))
                return ChatCompletionResult(data=data, model=resolved_model or candidate_model)
            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                if _should_try_next_model(exc):
                    advance_model = True
                    break
                should_retry = (
                    isinstance(exc, (requests.Timeout, requests.ConnectionError, json.JSONDecodeError))
                    or getattr(getattr(exc, "response", None), "status_code", None) in {408, 409, 425, 429, 500, 502, 503, 504}
                )
                if attempt >= config.max_retries or not should_retry:
                    break
                base = min(2 ** (attempt - 1), AI_TEXT_RETRY_BACKOFF_MAX)
                time.sleep(base + random.uniform(0, base * 0.2))

        if advance_model:
            continue
        break

    failed_config = replace(config, model=attempted_model)
    raise AITextRequestError(
        failed_config,
        attempts=attempts,
        last_error=last_error or RuntimeError("unknown error"),
    ) from last_error


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

    reasoning = message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    raise RuntimeError("Unable to extract text from AI text response.")
