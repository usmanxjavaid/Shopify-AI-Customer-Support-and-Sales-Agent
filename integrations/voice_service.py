"""
integrations/voice_service.py
--------------------------------
Shared speech-to-text and text-to-speech functions, used by BOTH
the Telegram adapter and the web adapter. Extracted here so voice
logic isn't duplicated per channel.

STT: Groq Whisper (accepts raw audio bytes in common formats)
TTS: Google AI Studio Gemini TTS (returns raw PCM, wrapped into WAV)
"""

import base64
import io
import wave
import requests

from config import settings
from logger import get_logger

logger = get_logger(__name__)


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """
    Transcribes raw audio bytes to text using Groq's Whisper API.

    Args:
        audio_bytes: Raw audio file bytes (ogg, mp3, wav, webm all work).
        filename:    Filename hint for the multipart upload (extension
                     helps Groq detect the format).

    Returns:
        Transcribed text, or empty string if transcription failed.
    """
    logger.info("Transcribing audio")

    try:
        response = requests.post(
            url="https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, "application/octet-stream")},
            data={"model": "whisper-large-v3"},
            timeout=30,
        )
        response.raise_for_status()

        text = response.json().get("text", "").strip()
        logger.info(f"Transcription result: {text}")
        return text

    except requests.exceptions.RequestException as e:
        logger.error(f"Audio transcription failed: {e}")
        return ""


async def synthesize_speech(text: str) -> bytes:
    """
    Converts text to speech using Google AI Studio's Gemini TTS API.

    Gemini's TTS returns raw PCM audio (16-bit, 24kHz, mono), which
    we wrap into a proper WAV container so it's valid, playable audio.

    Args:
        text: The text to convert to speech.

    Returns:
        WAV-formatted audio bytes, or empty bytes if synthesis failed.
    """
    logger.info("Synthesizing speech")

    try:
        response = requests.post(
            url=(
                "https://generativelanguage.googleapis.com/v1beta/"
                "models/gemini-2.5-flash-preview-tts:generateContent"
                f"?key={settings.GOOGLE_AI_API_KEY}"
            ),
            json={
                "contents": [{"parts": [{"text": text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": "Kore"}
                        }
                    },
                },
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        audio_b64 = (
            data["candidates"][0]["content"]["parts"][0]
            ["inlineData"]["data"]
        )
        pcm_bytes = base64.b64decode(audio_b64)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_bytes)

        logger.info("Speech synthesis succeeded")
        return wav_buffer.getvalue()

    except Exception as e:
        logger.error(f"Speech synthesis failed: {e}")
        return b""


logger.debug("integrations.voice_service loaded successfully")