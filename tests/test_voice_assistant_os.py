"""Comprehensive Unit Tests for Real-Time Voice Assistant OS Layer."""

import pytest
from zero_core.interfaces.telegram.bot import TelegramBotHandler
from zero_core.interfaces.voice import (
    AudioTranscriber,
    SpeechSynthesizer,
    VoiceSessionCoordinator,
)
from zero_core.memory.session import SessionMemory


def test_audio_transcriber_handling():
    transcriber = AudioTranscriber()

    # Empty payload check
    res_empty = transcriber.transcribe(b"")
    assert res_empty["success"] is False
    assert "Empty" in res_empty["error"]

    # Valid audio bytes
    fake_audio = b"\x00\x01\x02\x03" * 20
    res = transcriber.transcribe(fake_audio, audio_format="wav")
    assert res["success"] is True
    assert "Transcribed voice task" in res["text"]
    assert res["format"] == "wav"
    assert res["bytes_processed"] == 80


def test_speech_synthesizer_handling():
    synthesizer = SpeechSynthesizer(voice_id="jarvis_tone")

    # Empty text check
    res_empty = synthesizer.synthesize("")
    assert res_empty["success"] is False

    # Valid text
    res = synthesizer.synthesize("Account equity is currently $1,000 USD.")
    assert res["success"] is True
    assert res["voice_id"] == "jarvis_tone"
    assert res["char_count"] > 10
    assert len(res["audio_bytes"]) > 0


def test_voice_session_coordinator_loop():
    mem = SessionMemory()
    coordinator = VoiceSessionCoordinator(session_memory=mem)

    fake_audio = b"VOICE_COMMAND_MOCK_PAYLOAD_12345"
    turn_res = coordinator.handle_voice_turn(fake_audio, audio_format="ogg")

    assert turn_res["success"] is True
    assert "Transcribed voice task" in turn_res["task_text"]
    assert len(turn_res["response_text"]) > 0
    assert turn_res["tts"]["success"] is True

    # Verify session memory recorded the user and assistant turns
    history = mem.get_history()
    assert len(history) >= 2
    assert history[-2].role == "user"
    assert history[-1].role == "assistant"


def test_telegram_voice_note_intake():
    bot = TelegramBotHandler()

    fake_voice_note = b"TELEGRAM_OGG_VOICE_NOTE_BYTES_12345678"
    reply = bot.handle_voice_note(fake_voice_note, audio_format="ogg")

    assert "🎙️ *Heard*:" in reply
    assert "👤 *Specialist*:" in reply
