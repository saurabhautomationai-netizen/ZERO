"""Production-grade LLM Provider integration for ZERO (Phase 2 & Priority 1).

Supports Gemini API, local Ollama, OpenAI, and offline mock fallbacks with zero
required third-party dependencies (built with standard library urllib/json).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class BaseLLMClient:
    """Base interface for model provider adapters."""

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        raise NotImplementedError


class MockOfflineLLMClient(BaseLLMClient):
    """Deterministic offline fallback client for testing and offline execution."""

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        specialist_name = "Agency Specialist"
        for line in system_prompt.splitlines():
            if line.startswith("name:"):
                specialist_name = line.replace("name:", "").strip()
                break

        return (
            f"[{specialist_name} Response]\n"
            f"Expert analysis for task: '{user_prompt}'\n"
            f"Grounding persona: {specialist_name} active."
        )


class GeminiLLMClient(BaseLLMClient):
    """Client for Google AI Gemini API via standard HTTPS endpoint."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "gemini-3.6-flash"):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.default_model = os.environ.get("GEMINI_MODEL", default_model)
        self.fallback_models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3-flash-preview"]

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        if not self.api_key:
            return "Gemini API Error: GEMINI_API_KEY is not set in environment or .env file."

        models_to_try = [model] if model else ([self.default_model] + [m for m in self.fallback_models if m != self.default_model])

        for target_model in models_to_try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
                f"?key={self.api_key}"
            )

            payload = {
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 2048,
                }
            }

            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    candidates = resp_json.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                    return "Gemini API: No text returned in candidate response."
            except urllib.error.HTTPError as err:
                # If 503 (High demand) or 429 (Rate limit), try next fallback model
                if err.code in (503, 429, 404):
                    continue
                err_msg = err.read().decode("utf-8") if err.fp else str(err)
                return f"Gemini API HTTP Error ({err.code}): {err_msg}"
            except Exception:
                continue

        return "⚠️ Gemini API: Models temporarily experiencing high demand. Please try again in a few moments."


class OllamaLLMClient(BaseLLMClient):
    """Client for local Ollama instances (e.g. Llama 3, Mistral, Nemotron)."""

    def __init__(self, host: str = "http://localhost:11434", default_model: str = "llama3"):
        self.host = os.environ.get("OLLAMA_HOST", host).rstrip("/")
        self.default_model = os.environ.get("OLLAMA_MODEL", default_model)

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        selected_model = model or self.default_model
        url = f"{self.host}/api/generate"

        payload = {
            "model": selected_model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                return resp_json.get("response", "Ollama: Empty response returned.")
        except Exception as exc:
            return f"Ollama Connection Error ({self.host}): {exc}"


class OpenAILLMClient(BaseLLMClient):
    """Client for OpenAI / compatible REST chat endpoints."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4o-mini"):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.default_model = default_model

    def generate(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> str:
        if not self.api_key:
            return "OpenAI Error: OPENAI_API_KEY is not set in environment or .env file."

        selected_model = model or self.default_model
        url = "https://api.openai.com/v1/chat/completions"

        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                choices = resp_json.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return "OpenAI: No choices returned."
        except urllib.error.HTTPError as err:
            err_msg = err.read().decode("utf-8") if err.fp else str(err)
            return f"OpenAI HTTP Error ({err.code}): {err_msg}"
        except Exception as exc:
            return f"OpenAI Connection Error: {exc}"


class LLMClientManager:
    """Manages active LLM provider configuration and specialist invocations."""

    def __init__(self, client: Optional[BaseLLMClient] = None):
        self._custom_client = client

    @property
    def client(self) -> BaseLLMClient:
        """Returns explicitly set client or auto-detects based on available environment credentials."""
        if self._custom_client is not None:
            return self._custom_client

        if os.environ.get("GEMINI_API_KEY"):
            return GeminiLLMClient()
        if os.environ.get("OPENAI_API_KEY"):
            return OpenAILLMClient()
        if os.environ.get("OLLAMA_MODEL"):
            return OllamaLLMClient()

        return MockOfflineLLMClient()

    def set_client(self, client: Optional[BaseLLMClient]) -> None:
        self._custom_client = client

    def call_specialist(self, persona: str, task: str, model: Optional[str] = None) -> str:
        """Invokes the active model client with specialist persona markdown as system instructions."""
        if not persona.strip():
            return f"Error: No persona markdown loaded for task: '{task}'."
        return self.client.generate(system_prompt=persona, user_prompt=task, model=model)


# Global singleton instance
DEFAULT_LLM_MANAGER = LLMClientManager()
