import httpx
import tempfile
import os
from config import OPENAI_API_KEY


def _detect_format(audio_bytes: bytes) -> tuple[str, str]:
    """Detect audio format from magic bytes. Returns (suffix, mime_type)."""
    if audio_bytes[:4] == b'OggS':
        return ".ogg", "audio/ogg"
    elif audio_bytes[:3] == b'ID3' or (len(audio_bytes) > 1 and audio_bytes[0] == 0xFF and audio_bytes[1] in (0xFB, 0xF3, 0xF2, 0xFA, 0xE3)):
        return ".mp3", "audio/mpeg"
    elif audio_bytes[:4] == b'RIFF':
        return ".wav", "audio/wav"
    elif audio_bytes[:4] == b'fLaC':
        return ".flac", "audio/flac"
    elif len(audio_bytes) > 8 and audio_bytes[4:8] == b'ftyp':
        return ".mp4", "audio/mp4"
    elif audio_bytes[:4] == b'\x1aE\xdf\xa3':  # WebM/MKV
        return ".webm", "audio/webm"
    else:
        # Unknown format - default to ogg (most common for WhatsApp)
        return ".ogg", "audio/ogg"


def _suffix_from_mime(mime_type: str) -> tuple[str, str]:
    """Fallback: map mime type to suffix."""
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
        return ".ogg", "audio/ogg"


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcribe audio from raw bytes using OpenAI Whisper."""
    # Try to detect format from actual file bytes first
    suffix, detected_mime = _detect_format(audio_bytes)

    # If detection says ogg but mime says mp4/m4a, trust the mime (ambiguous magic bytes)
    if suffix == ".ogg" and any(x in mime_type.lower() for x in ["mp4", "m4a", "mpeg", "mp3"]):
        suffix, detected_mime = _suffix_from_mime(mime_type)

    print(f"DEBUG transcribe: mime_type={mime_type}, detected={suffix}, size={len(audio_bytes)}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        with open(temp_path, "rb") as audio_file:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": (f"audio{suffix}", audio_file, detected_mime)},
                    data={"model": "whisper-1", "language": "he"},
                )
                if not resp.is_success:
                    print(f"ERROR transcribe {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json().get("text", "")
    finally:
        os.unlink(temp_path)
