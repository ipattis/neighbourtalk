import os
import base64
import subprocess
import tempfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neighbourtalk")

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from openai import OpenAI, OpenAIError
import deepl
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
if not DEEPL_API_KEY:
    raise RuntimeError("DEEPL_API_KEY is not set. Add it to your .env file.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
deepl_translator = deepl.Translator(DEEPL_API_KEY)

app = FastAPI(title="NeighbourTalk")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/translate")
async def translate_audio(
    audio: UploadFile = File(...),
    direction: str = Form(...),
):
    """
    Accepts an audio recording and a direction ('en-ro' or 'ro-en').
    Transcribes via Whisper, translates via DeepL, synthesises via OpenAI TTS.
    Returns JSON: { original, translated, audio_b64 }
    API keys are never exposed to the client.
    """
    if direction not in ("en-ro", "ro-en"):
        raise HTTPException(status_code=400, detail="direction must be 'en-ro' or 'ro-en'")

    if direction == "en-ro":
        whisper_language = "en"
        deepl_target_lang = "RO"
        tts_voice = "alloy"       # English output voice
    else:
        whisper_language = "ro"
        deepl_target_lang = "EN-US"
        tts_voice = "nova"        # Romanian output voice

    audio_data = await audio.read()
    mime_type = audio.content_type or "audio/webm"
    ext = _ext_for_mime(mime_type)
    filename = f"recording.{ext}"

    logger.info("Received audio: %d bytes, content-type=%s, filename=%s, direction=%s",
                len(audio_data), mime_type, filename, direction)

    if len(audio_data) < 500:
        logger.warning("Rejected: audio too short (%d bytes)", len(audio_data))
        raise HTTPException(status_code=400, detail="Audio clip too short. Try speaking for a moment.")

    # Step 1 — Transcribe
    original_text = _transcribe(audio_data, filename, whisper_language)

    # Step 2 — Translate
    translated_text = _translate(original_text, deepl_target_lang)

    # Step 3 — Text-to-speech
    audio_b64 = _tts(translated_text, tts_voice)

    return JSONResponse({
        "original": original_text,
        "translated": translated_text,
        "audio_b64": audio_b64,
    })


# ---------------------------------------------------------------------------
# Internal helpers (synchronous — called from async handler; fine for LAN-scale
# concurrency; wrap in run_in_executor if scaling beyond a few sessions)
# ---------------------------------------------------------------------------

def _transcribe(audio_data: bytes, filename: str, language: str) -> str:
    """Transcribe audio bytes using OpenAI Whisper (whisper-1)."""
    mime = _mime_for_filename(filename)
    try:
        response = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_data, mime),
            language=language,
        )
        text = response.text.strip()
    except OpenAIError as e:
        logger.error("Whisper error (will try ffmpeg fallback): %s", e)
        # Fall back to ffmpeg conversion → WAV and retry once
        try:
            text = _transcribe_via_ffmpeg(audio_data, language)
        except Exception as fe:
            logger.error("ffmpeg fallback also failed: %s", fe)
            raise HTTPException(
                status_code=502,
                detail=f"Transcription failed: {e}. ffmpeg fallback error: {fe}",
            )

    if not text:
        logger.warning("Whisper returned empty transcript")
        raise HTTPException(status_code=400, detail="No speech detected. Please try again.")

    return text


def _transcribe_via_ffmpeg(audio_data: bytes, language: str) -> str:
    """Convert audio to 16 kHz mono WAV via ffmpeg, then retry Whisper."""
    with tempfile.NamedTemporaryFile(suffix=".input", delete=False) as f:
        f.write(audio_data)
        tmp_in = f.name

    tmp_out = tmp_in + ".wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in, "-ar", "16000", "-ac", "1", "-f", "wav", tmp_out],
            check=True,
            capture_output=True,
            timeout=20,
        )
        with open(tmp_out, "rb") as wf:
            wav_data = wf.read()

        resp = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=("recording.wav", wav_data, "audio/wav"),
            language=language,
        )
        return resp.text.strip()
    finally:
        for p in (tmp_in, tmp_out):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass


def _translate(text: str, target_lang: str) -> str:
    """Translate text using DeepL. Formality not supported for all languages."""
    try:
        try:
            result = deepl_translator.translate_text(
                text, target_lang=target_lang, formality="prefer_less"
            )
        except Exception:
            # Romanian (RO) does not support the formality parameter — retry without it
            result = deepl_translator.translate_text(text, target_lang=target_lang)
        return result.text
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Translation failed: {e}")


def _tts(text: str, voice: str) -> str:
    """Synthesise speech with OpenAI TTS and return base64-encoded MP3."""
    try:
        response = openai_client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            response_format="mp3",
        )
        return base64.b64encode(response.content).decode("utf-8")
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")


def _ext_for_mime(mime: str) -> str:
    mime = mime.lower()
    if "mp4" in mime or "m4a" in mime:
        return "mp4"
    if "ogg" in mime:
        return "ogg"
    if "wav" in mime:
        return "wav"
    if "mpeg" in mime or mime.endswith("mp3"):
        return "mp3"
    return "webm"


def _mime_for_filename(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {
        "webm": "audio/webm",
        "mp4":  "audio/mp4",
        "m4a":  "audio/mp4",
        "ogg":  "audio/ogg",
        "wav":  "audio/wav",
        "mp3":  "audio/mpeg",
    }.get(ext, "audio/webm")
