"""Voice Interface package for ZERO (Milestone M19 & Voice OS Layer)."""

from zero_core.interfaces.voice.session_coordinator import (
    DEFAULT_VOICE_SESSION_COORDINATOR,
    VoiceSessionCoordinator,
)
from zero_core.interfaces.voice.synthesizer import (
    DEFAULT_SPEECH_SYNTHESIZER,
    SpeechSynthesizer,
)
from zero_core.interfaces.voice.transcriber import (
    DEFAULT_AUDIO_TRANSCRIBER,
    AudioTranscriber,
)

__all__ = [
    "AudioTranscriber",
    "SpeechSynthesizer",
    "VoiceSessionCoordinator",
    "DEFAULT_AUDIO_TRANSCRIBER",
    "DEFAULT_SPEECH_SYNTHESIZER",
    "DEFAULT_VOICE_SESSION_COORDINATOR",
]
