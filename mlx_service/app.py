from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request

try:
    from lightning_whisper_mlx import LightningWhisperMLX
except ImportError as exc:
    raise SystemExit(
        "lightning-whisper-mlx is not installed. Run: pip install -r mlx_service/requirements.txt"
    ) from exc

APP = Flask(__name__)

HOST = os.environ.get("MLX_SERVICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("MLX_SERVICE_PORT", "9001"))
SHARED_ROOT = Path(
    os.environ.get("MLX_SHARED_ROOT", str(Path.home() / "Downloads"))
).expanduser().resolve()
ALLOW_ABSOLUTE_PATHS = os.environ.get("MLX_ALLOW_ABSOLUTE_PATHS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
DEFAULT_MODEL = os.environ.get("MLX_DEFAULT_MODEL", "large-v3").strip() or "large-v3"
DEFAULT_BATCH_SIZE = int(os.environ.get("MLX_DEFAULT_BATCH_SIZE", "12"))
DEFAULT_QUANT = os.environ.get("MLX_DEFAULT_QUANT", "4bit").strip() or None
MODEL_WORKDIR = Path(
    os.environ.get("MLX_MODEL_WORKDIR", str(Path(__file__).resolve().parent))
).expanduser().resolve()

# lightning-whisper-mlx downloads into ./mlx_models relative to the process cwd.
MODEL_WORKDIR.mkdir(parents=True, exist_ok=True)
os.chdir(MODEL_WORKDIR)

SECONDS_PER_SEEK = 0.01
model_cache: dict[tuple[str, int, str | None], LightningWhisperMLX] = {}
model_lock = threading.Lock()


def bool_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in {"0", "false", "no", "off"}


def resolve_audio_path(payload: dict) -> Path:
    relative_path = str(payload.get("audio_relative_path") or "").strip()
    if relative_path:
        candidate = (SHARED_ROOT / relative_path).resolve()
        try:
            candidate.relative_to(SHARED_ROOT)
        except ValueError as exc:
            raise ValueError(f"Audio path escapes shared root: {relative_path}")
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Shared audio file not found: {candidate}")
        return candidate

    absolute_path = str(payload.get("audio_path") or "").strip()
    if absolute_path and ALLOW_ABSOLUTE_PATHS:
        candidate = Path(absolute_path).expanduser().resolve()
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Audio file not found: {candidate}")
        return candidate

    raise ValueError("No valid audio path was provided.")


def get_model(model_name: str, batch_size: int, quant: str | None) -> LightningWhisperMLX:
    key = (model_name, batch_size, quant)
    with model_lock:
        model = model_cache.get(key)
        if model is not None:
            return model
        model = LightningWhisperMLX(model=model_name, batch_size=batch_size, quant=quant)
        model_cache[key] = model
        return model


def convert_segments(raw_segments: list) -> list[dict]:
    converted = []
    for item in raw_segments or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        try:
            start = max(0.0, float(item[0]) * SECONDS_PER_SEEK)
            end = max(start, float(item[1]) * SECONDS_PER_SEEK)
        except (TypeError, ValueError):
            continue
        text = str(item[2] or "").strip()
        if not text:
            continue
        converted.append({"start": start, "end": end, "text": text})
    return converted


@APP.errorhandler(Exception)
def handle_error(exc):
    return jsonify({"ok": False, "error": str(exc)}), 500


@APP.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "mlx-whisper",
            "shared_root": str(SHARED_ROOT),
            "default_model": DEFAULT_MODEL,
            "default_batch_size": DEFAULT_BATCH_SIZE,
            "default_quant": DEFAULT_QUANT,
            "allow_absolute_paths": ALLOW_ABSOLUTE_PATHS,
            "cached_models": [json.dumps(item, ensure_ascii=False) for item in model_cache.keys()],
        }
    )


@APP.post("/api/transcribe")
def transcribe():
    payload = request.get_json(force=True, silent=True) or {}
    audio_path = resolve_audio_path(payload)
    language = str(payload.get("language") or "").strip() or None
    model_name = str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    batch_size = int(payload.get("batch_size") or DEFAULT_BATCH_SIZE)
    quant = str(payload.get("quant") or DEFAULT_QUANT or "").strip() or None

    start_time = time.time()
    whisper = get_model(model_name, batch_size, quant)
    result = whisper.transcribe(audio_path=str(audio_path), language=language)
    text = str(result.get("text") or "").strip()
    segments = convert_segments(result.get("segments") or [])
    if not segments and text:
        segments = [{"start": 0.0, "end": 0.0, "text": text}]

    return jsonify(
        {
            "ok": True,
            "audio_path": str(audio_path),
            "language": str(result.get("language") or language or "auto"),
            "text": text,
            "segments": segments,
            "source": "remote-mlx",
            "source_detail": (
                f"lightning-whisper-mlx model={model_name} quant={quant or 'base'} "
                f"batch={batch_size}"
            ),
            "backend": {
                "service": "lightning-whisper-mlx",
                "model": model_name,
                "batch_size": batch_size,
                "quant": quant,
            },
            "elapsed_seconds": round(time.time() - start_time, 3),
        }
    )


def main() -> None:
    SHARED_ROOT.mkdir(parents=True, exist_ok=True)
    APP.run(host=HOST, port=PORT, threaded=True)


if __name__ == "__main__":
    main()
