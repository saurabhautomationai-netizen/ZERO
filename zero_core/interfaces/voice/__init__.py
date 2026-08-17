"""Voice Interface package for ZERO (Milestone M19)."""

from zero_core.interfaces.voice.synthesizer import SpeechSynthesizer
from zero_core.interfaces.voice.transcriber import AudioTranscriber

__all__ = [
    "AudioTranscriber",
    "SpeechSynthesizer",
]
