from __future__ import annotations

from zero_core.interfaces.voice import AudioTranscriber, SpeechSynthesizer


def test_audio_transcriber():
    transcriber = AudioTranscriber()
    res = transcriber.transcribe(b"fake_audio_wav_data_12345", audio_format="wav")
    assert res["success"] is True
    assert "Transcribed voice task" in res["text"]
    assert res["format"] == "wav"

    empty_res = transcriber.transcribe(b"")
    assert empty_res["success"] is False


def test_speech_synthesizer():
    synthesizer = SpeechSynthesizer(voice_id="zero_voice_en")
    res = synthesizer.synthesize("Your portfolio status is green.")
    assert res["success"] is True
    assert res["voice_id"] == "zero_voice_en"
    assert res["payload_bytes"] > 0

    empty_res = synthesizer.synthesize("")
    assert empty_res["success"] is False
