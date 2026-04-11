import io
import tempfile
import os
from openai import OpenAI
from config import OPENAI_API_KEY

_openai_client = OpenAI(api_key=OPENAI_API_KEY)


def _detect_format(audio_bytes: bytes) -> str:
    """Detect audio format from magic bytes. Returns file suffix."""
    if audio_bytes[:4] == b'OggS':
        return ".ogg"
    elif audio_bytes[:3] == b'ID3' or (len(audio_bytes) > 1 and audio_bytes[0] == 0xFF and audio_bytes[1] in (0xFB, 0xF3, 0xF2, 0xFA, 0xE3)):
        return ".mp3"
    elif audio_bytes[:4] == b'RIFF':
        return ".wav"
    elif audio_bytes[:4] == b'fLaC':
        return ".flac"
    elif len(audio_bytes) > 8 and audio_bytes[4:8] == b'ftyp':
        return ".m4a"
    elif audio_bytes[:4] == b'\x1aE\xdf\xa3':  # WebM/MKV
        return ".webm"
    else:
        return ".ogg"


def _suffix_from_mime(mime_type: str) -> str:
    """Fallback: map mime type to suffix."""
    mime = mime_type.lower()
    if "ogg" in mime:
        return ".ogg"
    elif "mp3" in mime or "mpeg" in mime:
        return ".mp3"
    elif "mp4" in mime or "m4a" in mime or "aac" in mime:
        return ".m4a"
    elif "wav" in mime:
        return ".wav"
    elif "webm" in mime:
        return ".webm"
    elif "flac" in mime:
        return ".flac"
    else:
        return ".ogg"


def _convert_to_mp3(audio_bytes: bytes, src_suffix: str) -> bytes:
    """Convert audio bytes to mp3 using pydub+ffmpeg."""
    from pydub import AudioSegment
    fmt = src_suffix.lstrip(".")
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
    buf = io.BytesIO()
    seg.export(buf, format="mp3")
    return buf.getvalue()


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcribe audio from raw bytes using OpenAI Whisper."""
    suffix = _detect_format(audio_bytes)

    # If magic bytes defaulted to ogg but mime says mp4/m4a/mp3, trust the mime
    if suffix == ".ogg" and any(x in mime_type.lower() for x in ["mp4", "m4a", "mpeg", "mp3"]):
        suffix = _suffix_from_mime(mime_type)

    print(f"DEBUG transcribe: mime_type={mime_type}, suffix={suffix}, size={len(audio_bytes)}")

    # Convert non-ogg/mp3/wav formats to mp3 via ffmpeg for reliability
    if suffix not in (".ogg", ".mp3", ".wav", ".flac", ".webm"):
        try:
            print(f"DEBUG converting {suffix} to mp3 via ffmpeg")
            audio_bytes = _convert_to_mp3(audio_bytes, suffix)
            suffix = ".mp3"
        except Exception as e:
            print(f"WARNING ffmpeg conversion failed: {e}, sending original")

    import io as _io
    buf = _io.BytesIO(audio_bytes)
    buf.name = f"audio{suffix}"

    try:
        transcription = _openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            language="he",
        )
        return transcription.text
    except Exception as e:
        print(f"ERROR transcribe (OpenAI SDK): {e}")
        raise
