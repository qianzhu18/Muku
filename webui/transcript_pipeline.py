import json
import re
from datetime import datetime, timezone
from pathlib import Path


def clean_transcript_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *([，。！？；：、])", r"\1", text)
    text = re.sub(r"([（《“]) ", r"\1", text)
    text = re.sub(r" ([）》”])", r"\1", text)
    text = re.sub(r"(\d) +([%℃])", r"\1\2", text)
    text = re.sub(r"(\d) +([年月日天次级个万亿元块分钟小时秒])", r"\1\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    merged = " ".join(lines)
    merged = re.sub(r" {2,}", " ", merged).strip()
    return _paragraphize(merged)


def render_markdown(
    *,
    title: str,
    source_url: str,
    provider: str,
    model: str,
    raw_text: str,
    clean_text: str,
) -> str:
    frontmatter = {
        "title": title,
        "source_url": source_url,
        "transcription_provider": provider,
        "transcription_model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.extend(
        [
            "---",
            "",
            f"# {title}",
            "",
            f"- 来源：{source_url}",
            f"- 转写：`{provider}` / `{model}`",
            "",
            "## 清洗稿",
            "",
            clean_text.strip(),
            "",
            "## 原始逐字稿",
            "",
            raw_text.strip(),
            "",
        ]
    )
    return "\n".join(lines)


def write_sidecar_files(
    *,
    audio_path: Path,
    source_url: str,
    provider: str,
    model: str,
    raw_text: str,
    clean_text: str,
    markdown_text: str,
    extra_meta: dict,
) -> dict[str, Path]:
    raw_path = audio_path.with_suffix(".raw.txt")
    clean_path = audio_path.with_suffix(".clean.txt")
    markdown_path = audio_path.with_suffix(".md")
    meta_path = audio_path.with_suffix(".transcript.json")

    raw_path.write_text(raw_text.strip() + "\n", encoding="utf-8")
    clean_path.write_text(clean_text.strip() + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_text.strip() + "\n", encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "audio_path": str(audio_path),
                "source_url": source_url,
                "provider": provider,
                "model": model,
                **extra_meta,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "raw_path": raw_path,
        "clean_path": clean_path,
        "markdown_path": markdown_path,
        "meta_path": meta_path,
    }


def _paragraphize(text: str, max_chars: int = 220) -> str:
    sentences = re.split(r"(?<=[。！？!?\.])\s+", text)
    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_len = len(sentence)
        if current and current_len + sentence_len > max_chars:
            paragraphs.append(" ".join(current).strip())
            current = [sentence]
            current_len = sentence_len
            continue
        current.append(sentence)
        current_len += sentence_len + 1

    if current:
        paragraphs.append(" ".join(current).strip())

    return "\n\n".join(paragraphs).strip()
