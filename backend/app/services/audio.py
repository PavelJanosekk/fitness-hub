"""Make browser recordings acceptable to Gemini (docs/SPEC.md §6.6, A8).

Android Chrome records audio/webm (Opus) and iOS Safari audio/mp4 (AAC); neither is on Gemini's documented
audio list, so those are transcoded with ffmpeg to 16 kHz mono FLAC (lossless, small for speech).
"""

import subprocess

# Gemini's documented audio MIME types (aliases normalized below)
GEMINI_AUDIO_TYPES = {"audio/wav", "audio/mp3", "audio/aiff", "audio/aac", "audio/ogg", "audio/flac"}
ALIASES = {
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/mpeg": "audio/mp3",
    "audio/x-flac": "audio/flac",
}
MAX_AUDIO_BYTES = 15 * 1024 * 1024  # inline request data must stay under Gemini's 20 MB limit
TRANSCODE_TIMEOUT_S = 30


class AudioError(ValueError):
    pass


def prepare_audio(data: bytes, mime_type: str | None) -> tuple[bytes, str]:
    """Return (bytes, mime type) Gemini accepts, transcoding when needed."""
    if not data:
        raise AudioError("Empty recording")
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioError("Recording too large")
    base = (mime_type or "").split(";", 1)[0].strip().lower()
    base = ALIASES.get(base, base)
    if base in GEMINI_AUDIO_TYPES:
        return data, base
    return transcode_to_flac(data), "audio/flac"


def transcode_to_flac(data: bytes) -> bytes:
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "flac",
                "pipe:1",
            ],
            input=data,
            capture_output=True,
            timeout=TRANSCODE_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        raise AudioError("ffmpeg is not installed") from None
    except subprocess.TimeoutExpired:
        raise AudioError("Transcoding timed out") from None
    if result.returncode != 0 or not result.stdout:
        raise AudioError(f"Could not decode the recording: {result.stderr.decode(errors='replace')[:200]}")
    return result.stdout
