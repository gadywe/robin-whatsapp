import httpx
import tempfile
import os
from config import OPENAI_API_KEY


def transcribe_audio(audio_url: str) -> str:
    """Download audio from Green API and transcribe with Whisper."""

    # Download the audio file
    with httpx.Client(timeout=60) as client:
        audio_resp = client.get(audio_url)
        audio_resp.raise_for_status()

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(audio_resp.content)
        temp_path = f.name

    try:
        # Send to Whisper API
        with open(temp_path, "rb") as audio_file:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": ("audio.ogg", audio_file, "audio/ogg")},
                    data={"model": "whisper-1", "language": "he"},
                )
                resp.raise_for_status()
                return resp.json().get("text", "")
    finally:
        os.unlink(temp_path)
