import json
import re
from pathlib import Path


TRANSCRIPT_METADATA_PATTERNS = [
    re.compile(r"^\s*---\s*$"),
    re.compile(r"^\s*(title|source_url|transcription_provider|transcription_model|generated_at)\s*:\s*.+$", re.IGNORECASE),
    re.compile(r"^\s*-\s*(来源|转写)\s*[:：].+$"),
]


def clean_transcript_text(text: str) -> str:
    text = strip_transcript_metadata(text)
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


def normalize_raw_transcript_text(text: str) -> str:
    text = strip_transcript_metadata(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_transcript_metadata(text: str) -> str:
    text = text.strip()
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if any(pattern.match(stripped) for pattern in TRANSCRIPT_METADATA_PATTERNS):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(r"^(来源|转写)\s*[:：].+$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def detect_platform(url: str) -> str:
    lowered = url.lower()
    if "bilibili.com" in lowered or "b23.tv" in lowered:
        return "Bilibili"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "YouTube"
    if "x.com" in lowered or "twitter.com" in lowered:
        return "X"
    return "Unknown"


def build_artifact_paths(base_path: Path) -> dict[str, Path]:
    stem = base_path.stem
    return {
        "raw_path": base_path.with_name(f"{stem} - 原始逐字稿.txt"),
        "article_path": base_path.with_name(f"{stem} - 解析稿.md"),
        "knowledge_path": base_path.with_name(f"{stem} - 知识库.md"),
        "markdown_path": base_path.with_name(f"{stem} - 逐字稿.md"),
        "meta_path": base_path.with_name(f"{stem} - 转写信息.json"),
    }


def render_markdown(
    *,
    title: str,
    clean_text: str,
    raw_text: str,
    article_text: str | None,
) -> str:
    sections = [
        f"# {title}",
        "",
        "## 清洗稿",
        "",
        clean_text.strip(),
        "",
        "## 原始稿",
        "",
        raw_text.strip(),
        "",
    ]

    if article_text and article_text.strip():
        sections.extend(
            [
                "## 解析稿",
                "",
                article_text.strip(),
                "",
            ]
        )

    return "\n".join(sections).strip() + "\n"


def write_sidecar_files(
    *,
    artifact_base_path: Path,
    source_url: str,
    provider: str,
    model: str,
    raw_text: str,
    clean_text: str,
    article_text: str | None,
    markdown_text: str,
    source_media_path: Path | None,
    extra_meta: dict,
) -> dict[str, Path]:
    paths = build_artifact_paths(artifact_base_path)
    legacy_clean_path = artifact_base_path.with_name(f"{artifact_base_path.stem} - 清洗逐字稿.txt")

    paths["markdown_path"].parent.mkdir(parents=True, exist_ok=True)

    paths["raw_path"].write_text(raw_text.strip() + "\n", encoding="utf-8")
    if legacy_clean_path.exists():
        legacy_clean_path.unlink()
    if article_text and article_text.strip():
        paths["article_path"].write_text(article_text.strip() + "\n", encoding="utf-8")
    elif paths["article_path"].exists():
        paths["article_path"].unlink()
    paths["markdown_path"].write_text(markdown_text.strip() + "\n", encoding="utf-8")
    paths["meta_path"].write_text(
        json.dumps(
            {
                "audio_path": str(source_media_path) if source_media_path else None,
                "artifact_base_path": str(artifact_base_path),
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

    return paths


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
