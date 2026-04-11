import httpx
import tempfile
import os
from config import OPENAI_API_KEY


def _get_suffix_and_mime(mime_type: str) -> tuple[str, str]:
    """Return (file_suffix, corrected_mime) for Whisper."""
    mime = mime_type.lower()
    if "ogg" in mime:
        return ".ogg", "audio/ogg"
    elif "mp3" in mime or "mpeg" in mime:
        return ".mp3", "audio/mpeg"
    elif "mp4" in mime or "m4a" in mime or "aac" in mime:
        return ".mp4", "audio/mp4"
    elif "wav" in mime:
        return ".wav", "audio/wav"
    elif "webm" in mime:
        return ".webm", "audio/webm"
    elif "flac" in mime:
        return ".flac", "audio/flac"
    else:
        # Default: try ogg (WhatsApp voice messages)
        return ".ogg", "audio/ogg"


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcribe audio from raw bytes using OpenAI Whisper."""
    suffix, corrected_mime = _get_suffix_and_mime(mime_type)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        with open(temp_path, "rb") as audio_file:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": (f"audio{suffix}", audio_file, corrected_mime)},
                    data={"model": "whisper-1", "language": "he"},
                )
                if not resp.is_success:
                    print(f"ERROR transcribe {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json().get("text", "")
    finally:
        os.unlink(temp_path)
