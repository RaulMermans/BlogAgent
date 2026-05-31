"""LLM provider implementations.

Each provider wraps a specific API client and returns a ProviderResponse.
Providers are selected and instantiated by the LLM client — do not call
provider classes directly from application code.

Supported providers:
  anthropic  — requires `anthropic` package + ANTHROPIC_API_KEY
  openai     — requires `openai` package + OPENAI_API_KEY
  google     — requires `google-genai` package + GOOGLE_API_KEY

Missing API keys or missing packages raise MissingAPIKeyError or
ImportError respectively; the LLM client catches both and falls back
to mock with a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MissingAPIKeyError(RuntimeError):
    """Raised when a required API key env var is not set."""


@dataclass
class ProviderResponse:
    text: str
    model: str
    provider: str


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self._model = model
        self.timeout = timeout

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2
    ) -> ProviderResponse:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "anthropic package is not installed. Run: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text
        return ProviderResponse(text=text, model=self._model, provider=self.name)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self._model = model
        self.timeout = timeout

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2
    ) -> ProviderResponse:
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError("openai package is not installed. Run: pip install openai") from exc

        client = openai.OpenAI(api_key=self.api_key, timeout=self.timeout)
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or ""
        return ProviderResponse(text=text, model=self._model, provider=self.name)


class GoogleProvider:
    name = "google"

    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self.api_key = api_key
        self._model = model
        self.timeout = timeout

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Safely concatenate text from all candidates and parts in a Gemini response.

        Falls back to response.text if the candidate structure is unavailable.
        """
        try:
            parts: list[str] = []
            for candidate in response.candidates or []:
                content = getattr(candidate, "content", None)
                if content is None:
                    continue
                for part in getattr(content, "parts", []) or []:
                    t = getattr(part, "text", None)
                    if t:
                        parts.append(t)
            if parts:
                return "".join(parts)
        except Exception:  # noqa: BLE001
            pass
        return response.text or ""

    def generate(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2
    ) -> ProviderResponse:
        try:
            from google import genai  # noqa: PLC0415
            from google.genai import types  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "google-genai package is not installed. Run: pip install google-genai"
            ) from exc

        client = genai.Client(api_key=self.api_key)

        # Try native structured JSON output; fall back to plain text JSON if unsupported.
        try:
            response = client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            text = self._extract_text(response)
        except Exception:  # noqa: BLE001
            # Some older model versions don't support response_mime_type; retry without it.
            response = client.models.generate_content(
                model=self._model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=types.GenerateContentConfig(temperature=temperature),
            )
            text = self._extract_text(response)

        return ProviderResponse(text=text, model=self._model, provider=self.name)
