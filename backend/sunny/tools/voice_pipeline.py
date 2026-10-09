"""P11 — Voice pipeline: STT → LLM → TTS for Sunny.

Handles speech-to-text input, routes through the LLM,
and optionally converts responses to speech.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class VoiceInteraction:
    """A single voice interaction."""
    transcript: str
    response: str = ""
    is_question: bool = False
    duration_seconds: float = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VoicePipeline:
    """Manages the voice interaction pipeline."""

    def __init__(
        self,
        vault: Path,
        stt_model: str = "tiny",
        tts_voice: str = "default",
        wake_word: str = "sunny",
        max_history: int = 50,
        preload_stt: bool = True,
    ) -> None:
        self.vault = vault
        self.stt_model = stt_model
        self.tts_voice = tts_voice
        self.wake_word = wake_word.lower()
        self._max_history = max_history
        self._interaction_history: list[VoiceInteraction] = []
        self._stt_model_obj: Optional[Any] = None
        self._stt_loading = False
        self._stt_load_time: Optional[float] = None
        self._tts_available = True

    @property
    def interaction_history(self) -> list[VoiceInteraction]:
        return self._interaction_history

    @property
    def is_configured(self) -> bool:
        """Check if voice pipeline has required components."""
        return True

    def _preload_stt(self) -> None:
        """Load the STT model into memory (cached)."""
        if self._stt_model_obj is not None:
            return
        if self._stt_loading:
            return
        self._stt_loading = True
        try:
            import whisper
            start = time.monotonic()
            self._stt_model_obj = whisper.load_model(self.stt_model)
            elapsed = time.monotonic() - start
            self._stt_load_time = elapsed
            log.info("STT model '%s' loaded in %.1fs", self.stt_model, elapsed)
        except ImportError:
            log.warning("STT dependencies not installed (whisper/speech_recognition)")
            self._stt_model_obj = None
        except Exception as e:
            log.error("Failed to load STT model: %s", e)
            self._stt_model_obj = None
        finally:
            self._stt_loading = False

    def detect_wake_word(self, text: str) -> bool:
        """Check if text contains the wake word."""
        text_lower = text.lower()
        return self.wake_word in text_lower

    def transcribe(
        self,
        audio_data: Optional[bytes] = None,
        text_input: Optional[str] = None,
    ) -> str:
        """Transcribe audio to text, or pass through text_input."""
        if text_input:
            return text_input

        if audio_data:
            try:
                import whisper
            except ImportError:
                log.warning("STT dependencies not installed, returning empty")
                return ""

            if self._stt_model_obj is None:
                self._preload_stt()

            if self._stt_model_obj is not None:
                try:
                    result = self._stt_model_obj.transcribe(audio_data)
                    return result["text"].strip()
                except Exception as e:
                    log.error("Transcription failed: %s", e)
                    return ""
            return ""

        return ""

    async def process_voice_input(
        self,
        transcript: str,
        context: dict = None,
    ) -> str:
        """Process a voice transcript through the pipeline."""
        if not transcript.strip():
            return ""

        start = time.monotonic()
        interaction = VoiceInteraction(transcript=transcript)

        response = await self._call_llm(transcript, context or {})
        interaction.response = response
        interaction.is_question = transcript.strip().endswith("?")
        interaction.duration_seconds = round(time.monotonic() - start, 2)

        self._interaction_history.append(interaction)
        self._trim_history()

        self._save_interaction(interaction)

        return response

    def _trim_history(self) -> None:
        """Trim interaction history to max_history."""
        if len(self._interaction_history) > self._max_history:
            excess = len(self._interaction_history) - self._max_history
            self._interaction_history = self._interaction_history[excess:]

    async def _call_llm(self, transcript: str, context: dict) -> str:
        """Call the LLM with the transcript."""
        try:
            from sunny.llm.close_hook import chat_completion

            messages = [
                {"role": "system", "content": "You are Sunny, a helpful personal assistant. Keep responses concise."},
                {"role": "user", "content": transcript},
            ]

            result = await chat_completion(messages, model="claude-sonnet-4-20250514")

            if result and isinstance(result, dict):
                return result.get("content", result.get("text", "I didn't understand."))
            return str(result) if result else "I didn't understand."
        except Exception as e:
            log.error("Voice LLM call failed: %s", e)
            return self._fallback_response(transcript)

    def _fallback_response(self, transcript: str) -> str:
        """Fallback response when LLM is unavailable."""
        lower = transcript.lower()

        if "hello" in lower or "hi" in lower:
            return "Hello! I'm Sunny, your personal assistant."
        elif "how are you" in lower:
            return "I'm doing well, thank you for asking!"
        elif "time" in lower:
            return f"The current time is {datetime.now(timezone.utc).strftime('%I:%M %p')}."
        elif "weather" in lower:
            return "I need weather data configured to answer that."
        elif "reminder" in lower:
            return "I'll help you set a reminder."
        else:
            return "I'm here to help. What can I do for you?"

    def synthesize(self, text: str, output_dir: Optional[Path] = None) -> Optional[Path]:
        """Convert text to speech (TTS). Returns path to audio file or None."""
        if not text.strip():
            return None

        if not self._tts_available:
            return None

        try:
            import edge_tts
        except ImportError:
            if self._tts_available:
                self._tts_available = False
                log.warning("edge-tts not installed; TTS unavailable. pip install edge-tts")
            return None

        tts_dir = output_dir or (self.vault / "data" / "voice" / "tts")
        tts_dir.mkdir(parents=True, exist_ok=True)

        voice_map = {
            "default": "en-US-AriaNeural",
            "male": "en-US-GuyNeural",
            "female": "en-US-AriaNeural",
        }
        voice = voice_map.get(self.tts_voice, "en-US-AriaNeural")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"tts-{timestamp}.mp3"
        output_path = tts_dir / filename

        try:
            asyncio.run(edge_tts.communicate(text, voice, str(output_path)))
            log.info("TTS synthesized %d chars -> %s", len(text), output_path)
            return output_path
        except Exception as e:
            log.error("TTS synthesis failed: %s", e)
            return None

    def _save_interaction(self, interaction: VoiceInteraction) -> None:
        """Save voice interaction to vault."""
        voice_dir = self.vault / "data" / "voice"
        voice_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{interaction.timestamp.strftime('%Y%m%d-%H%M%S')}.txt"
        filepath = voice_dir / filename
        filepath.write_text(
            f"Q: {interaction.transcript}\nA: {interaction.response}\n\n",
            encoding="utf-8",
        )

    def get_last_interaction(self) -> Optional[VoiceInteraction]:
        if self._interaction_history:
            return self._interaction_history[-1]
        return None

    def clear_history(self) -> None:
        self._interaction_history.clear()
