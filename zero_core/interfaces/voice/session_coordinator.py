"""Voice session coordinator managing the voice-to-execution-to-speech loop."""

from __future__ import annotations

from typing import Any, Dict, Optional

from zero_core.bootstrap import build_orchestrator
from zero_core.interfaces.voice.synthesizer import (
    DEFAULT_SPEECH_SYNTHESIZER,
    SpeechSynthesizer,
)
from zero_core.interfaces.voice.transcriber import (
    DEFAULT_AUDIO_TRANSCRIBER,
    AudioTranscriber,
)
from zero_core.memory.session import DEFAULT_SESSION_MEMORY, SessionMemory
from zero_core.orchestrator import Orchestrator


class VoiceSessionCoordinator:
    """Coordinates incoming audio intake, agent task execution, session memory, and voice synthesis."""

    def __init__(
        self,
        transcriber: Optional[AudioTranscriber] = None,
        synthesizer: Optional[SpeechSynthesizer] = None,
        orchestrator: Optional[Orchestrator] = None,
        session_memory: Optional[SessionMemory] = None,
    ):
        self.transcriber = transcriber or DEFAULT_AUDIO_TRANSCRIBER
        self.synthesizer = synthesizer or DEFAULT_SPEECH_SYNTHESIZER
        self.orchestrator = orchestrator or build_orchestrator()
        self.session_memory = session_memory or DEFAULT_SESSION_MEMORY

    def handle_voice_turn(
        self,
        audio_bytes: bytes,
        audio_format: str = "wav",
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """Executes a full audio-in to audio-out conversational loop."""
        # 1. Transcribe
        trans_res = self.transcriber.transcribe(audio_bytes, audio_format)
        if not trans_res.get("success") or not trans_res.get("text"):
            return {
                "success": False,
                "error": trans_res.get("error", "Transcription failed"),
                "task_text": "",
                "response_text": "",
            }

        task_text = trans_res["text"]

        # Record user utterance in session memory
        self.session_memory.add_turn(role="user", content=task_text)

        # 2. Execute via Orchestrator
        outcome = self.orchestrator.execute(task_text)
        answer_text = outcome.answer

        # If LLM needed for agency specialist
        if outcome.needs_llm and outcome.persona and answer_text is None:
            from zero_core.llm import DEFAULT_LLM_MANAGER
            answer_text = DEFAULT_LLM_MANAGER.call_specialist(persona=outcome.persona, task=task_text)

        final_answer = answer_text or f"Specialist assigned for {task_text}."

        # Record assistant response in session memory
        self.session_memory.add_turn(role="assistant", content=final_answer)

        # 3. Synthesize Speech
        tts_res = self.synthesizer.synthesize(final_answer)

        return {
            "success": True,
            "task_text": task_text,
            "response_text": final_answer,
            "selected_agent": outcome.spec.name if outcome.spec else "Orchestrator",
            "agent_slug": outcome.spec.slug if outcome.spec else None,
            "transcription_engine": trans_res.get("engine", "offline"),
            "tts": tts_res,
        }


# Global singleton instance
DEFAULT_VOICE_SESSION_COORDINATOR = VoiceSessionCoordinator()
