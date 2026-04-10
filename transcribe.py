import httpx
import tempfile
import os
from config import OPENAI_API_KEY


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcribe audio from raw bytes using OpenAI Whisper."""
    suffix = ".ogg" if "ogg" in mime_type else ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name
    try:
        with open(temp_path, "rb") as audio_file:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": (f"audio{suffix}", audio_file, mime_type)},
                    data={"model": "whisper-1", "language": "he"},
                )
                resp.raise_for_status()
                return resp.json().get("text", "")
    finally:
        os.unlink(temp_path)
