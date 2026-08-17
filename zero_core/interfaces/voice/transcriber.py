"""Voice input transcriber and intake interface for ZERO (Milestone M19)."""

from __future__ import annotations

from typing import Any, Dict, Optional


class AudioTranscriber:
    """Processes incoming audio payloads into task strings."""

    def __init__(self, model_name: str = "whisper_mock_offline"):
        self.model_name = model_name

    def transcribe(self, audio_bytes: bytes, audio_format: str = "wav") -> Dict[str, Any]:
        """Transcribes raw audio bytes into formatted task text."""
        if not audio_bytes:
            return {"success": False, "error": "Empty audio payload", "text": ""}

        # Offline deterministic conversion for tests and fallback
        text_estimate = f"Transcribed voice task ({len(audio_bytes)} bytes, format={audio_format})"
        return {
            "success": True,
            "text": text_estimate,
            "format": audio_format,
            "bytes_processed": len(audio_bytes),
        }
