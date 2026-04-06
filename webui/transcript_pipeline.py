from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass

CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")
NUMERIC_UNIT_RE = re.compile(
    r"(?<=\d)\s+(?=(?:年|月|日|号|点|分|秒|次|倍|个|集|章|页|岁|天|周|分钟|小时|万元|亿元|万|千|百|元|块|mAh|MB|GB|TB|KB|Hz|kHz|MHz|GHz))"
)
NUMERIC_SYMBOL_RE = re.compile(r"(?<=\d)\s*([.,:%/xX+-])\s*(?=\d)")
SENTENCE_END_RE = re.compile(r"[。！？!?…]$")


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptParagraph:
    start: float
    end: float
    text: str


def clean_transcript_text(text: str) -> str:
    cleaned = (text or "").replace("\u3000", " ").replace("\xa0", " ").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", cleaned)
    cleaned = NUMERIC_UNIT_RE.sub("", cleaned)
    cleaned = NUMERIC_SYMBOL_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"(?<=\d)\s*(%|％)", "%", cleaned)
    cleaned = re.sub(r"([¥$€])\s+(?=\d)", r"\1", cleaned)
    cleaned = re.sub(r"(?<=\d)\s+([万亿千百])", r"\1", cleaned)
    cleaned = re.sub(r"第\s+(\d+)\s*(?=(?:章|节|集|季|页|课|回|部分))", r"第\1", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：、,.!?%])", r"\1", cleaned)
    cleaned = re.sub(r"([（【《“‘])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([）】》”’])", r"\1", cleaned)
    cleaned = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", cleaned)
    cleaned = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=\d)", "", cleaned)
    cleaned = re.sub(r"(?<=\d)\s+(?=[\u3400-\u9fff])", "", cleaned)
    cleaned = re.sub(r"([，。！？；：、])\s+(?=[\u3400-\u9fff])", r"\1", cleaned)
    cleaned = re.sub(r"([，。！？；：、])(?=[A-Za-z0-9])", r"\1 ", cleaned)
    return cleaned.strip()


def strip_subtitle_markup(text: str) -> str:
    cleaned = html.unescape((text or "").strip())
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = cleaned.replace("\u200b", "").replace("\ufeff", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def coerce_segments(segments) -> list[TranscriptSegment]:
    coerced = []
    for segment in segments:
        text = strip_subtitle_markup(str(getattr(segment, "text", "") or ""))
        if not text:
            continue
        coerced.append(
            TranscriptSegment(
                start=float(getattr(segment, "start", 0.0) or 0.0),
                end=float(getattr(segment, "end", 0.0) or 0.0),
                text=text,
            )
        )
    return coerced


def normalize_segments(segments) -> list[TranscriptSegment]:
    normalized = []
    for segment in coerce_segments(segments):
        text = clean_transcript_text(segment.text)
        if not text:
            continue
        normalized.append(
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=text,
            )
        )
    return normalized


def join_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left.endswith((" ", "\n")) or right.startswith((" ", "\n")):
        return left + right
    if re.match(r"^[，。！？；：、,.!?)]", right):
        return left + right
    if CJK_CHAR_RE.search(left[-1]) or CJK_CHAR_RE.match(right[0]):
        return left + right
    return left + " " + right


def build_plain_text(segments: list[TranscriptSegment], clean: bool = True) -> str:
    segments = normalize_segments(segments) if clean else coerce_segments(segments)
    text = ""
    for segment in segments:
        text = join_text(text, segment.text)
    return text.strip()


def build_paragraphs(
    segments: list[TranscriptSegment],
    target_chars: int = 220,
    hard_limit: int = 320,
    gap_seconds: float = 1.6,
    clean: bool = True,
) -> list[TranscriptParagraph]:
    segments = normalize_segments(segments) if clean else coerce_segments(segments)
    paragraphs: list[TranscriptParagraph] = []
    buffer: list[TranscriptSegment] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        text = ""
        for segment in buffer:
            text = join_text(text, segment.text)
        paragraphs.append(
            TranscriptParagraph(
                start=buffer[0].start,
                end=buffer[-1].end,
                text=text.strip(),
            )
        )
        buffer = []

    for segment in segments:
        if buffer:
            last = buffer[-1]
            current_text = build_plain_text(buffer)
            should_flush = False

            if segment.start - last.end > gap_seconds:
                should_flush = True
            elif len(current_text) >= hard_limit:
                should_flush = True
            elif len(current_text) >= target_chars and SENTENCE_END_RE.search(last.text):
                should_flush = True

            if should_flush:
                flush()

        buffer.append(segment)

    flush()
    return paragraphs


def format_note_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_markdown_note(
    *,
    title: str,
    source_url: str,
    source_id: str,
    source_platform: str,
    preset: str,
    created_at: str,
    transcript_language: str,
    transcript_model: str,
    transcript_source: str,
    transcript_source_detail: str | None,
    audio_name: str,
    txt_name: str,
    srt_name: str,
    raw_txt_name: str | None,
    raw_srt_name: str | None,
    segments: list[TranscriptSegment],
    paragraph_chars: int,
    paragraph_gap_seconds: float,
) -> str:
    paragraphs = build_paragraphs(
        segments,
        target_chars=paragraph_chars,
        gap_seconds=paragraph_gap_seconds,
    )
    platform_tag = (source_platform or "unknown").strip().lower().replace(" ", "-")
    if not platform_tag:
        platform_tag = "unknown"

    source_lines = [
        f"- 平台：{source_platform}",
        f"- 链接：{source_url}",
        f"- 来源 ID：{source_id}",
        f"- 生成时间：{created_at}",
        f"- 识别语言：{transcript_language}",
        f"- 模型：{transcript_model}",
        f"- 转写来源：{transcript_source}",
    ]
    if transcript_source_detail:
        source_lines.append(f"- 来源详情：{transcript_source_detail}")

    attachment_lines = [
        f"- [音频](./{audio_name})",
        f"- [纯文本](./{txt_name})",
        f"- [字幕](./{srt_name})",
    ]
    if raw_txt_name:
        attachment_lines.append(f"- [原始纯文本](./{raw_txt_name})")
    if raw_srt_name:
        attachment_lines.append(f"- [原始字幕](./{raw_srt_name})")

    lines = [
        "---",
        f"title: {yaml_quote(title)}",
        f"source_url: {yaml_quote(source_url)}",
        f"source_id: {yaml_quote(source_id)}",
        f"source_platform: {yaml_quote(source_platform)}",
        f"created_at: {yaml_quote(created_at)}",
        f"preset: {yaml_quote(preset)}",
        f"transcript_language: {yaml_quote(transcript_language)}",
        f"transcript_model: {yaml_quote(transcript_model)}",
        "tags:",
        '  - "transcript"',
        f"  - {yaml_quote(platform_tag)}",
        "---",
        "",
        f"# {title}",
        "",
        "## 来源",
        *source_lines,
        "",
        "## 附件",
        *attachment_lines,
        "",
        "## 清洗说明",
        "- 合并被 Whisper 切开的数字空格",
        "- 统一常见数字与单位、百分号、时间符号的写法",
        "- 将短分句合并为更适合 Markdown 笔记阅读的段落",
        "",
        "## 逐字稿",
        "",
    ]

    if not paragraphs:
        lines.append("_未识别到有效语音内容。_")
        return "\n".join(lines) + "\n"

    for paragraph in paragraphs:
        lines.append(f"### {format_note_timestamp(paragraph.start)}")
        lines.append(paragraph.text)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_srt_segments(content: str, clean: bool = True) -> list[TranscriptSegment]:
    chunks = re.split(r"\n\s*\n", (content or "").strip())
    segments: list[TranscriptSegment] = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 3:
            continue

        timestamp_line = lines[1]
        if "-->" not in timestamp_line:
            continue
        start_text, end_text = [part.strip() for part in timestamp_line.split("-->", 1)]
        text = strip_subtitle_markup(" ".join(lines[2:]))
        if clean:
            text = clean_transcript_text(text)
        if not text:
            continue

        segments.append(
            TranscriptSegment(
                start=parse_srt_timestamp(start_text),
                end=parse_srt_timestamp(end_text),
                text=text,
            )
        )
    return segments


def parse_vtt_segments(content: str, clean: bool = True) -> list[TranscriptSegment]:
    normalized_content = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    chunks = re.split(r"\n\s*\n", normalized_content)
    segments: list[TranscriptSegment] = []

    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue

        timestamp_line = None
        text_lines = []
        if "-->" in lines[0]:
            timestamp_line = lines[0]
            text_lines = lines[1:]
        elif len(lines) > 1 and "-->" in lines[1]:
            timestamp_line = lines[1]
            text_lines = lines[2:]
        if not timestamp_line:
            continue

        start_text, end_part = [part.strip() for part in timestamp_line.split("-->", 1)]
        end_text = end_part.split()[0]
        text = strip_subtitle_markup(" ".join(text_lines))
        if clean:
            text = clean_transcript_text(text)
        if not text:
            continue

        segments.append(
            TranscriptSegment(
                start=parse_vtt_timestamp(start_text),
                end=parse_vtt_timestamp(end_text),
                text=text,
            )
        )

    return segments


def parse_srt_timestamp(value: str) -> float:
    match = re.fullmatch(r"(\d+):(\d+):(\d+),(\d+)", value.strip())
    if not match:
        return 0.0
    hours, minutes, seconds, millis = (int(item) for item in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_vtt_timestamp(value: str) -> float:
    match = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+)\.(\d+)", value.strip())
    if not match:
        return 0.0
    hours_text, minutes, seconds, millis = match.groups()
    hours = int(hours_text or 0)
    return hours * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def load_segments_from_subtitle_file(path, clean: bool = True) -> list[TranscriptSegment]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt_segments(content, clean=clean)
    if suffix == ".vtt":
        return parse_vtt_segments(content, clean=clean)
    raise ValueError(f"Unsupported subtitle format: {path}")
