"""
sapt.ai.providers
AI provider implementations — Anthropic, OpenAI, Gemini, and generic
OpenAI-compatible endpoints.

Each provider handles its own request format and response parsing,
exposing a unified call(system_prompt, user_message) → dict interface.
"""

import json
import requests
from abc import ABC, abstractmethod

from sapt.utils.constants import DEFAULT_MAX_TOKENS


class ProviderError(Exception):
    """Raised when an AI provider call fails."""
    pass


class BaseProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, config: dict):
        self.endpoint = config["endpoint"]
        self.model = config["model"]
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout", 30)
        self.structured_output = config.get("structured_output", True)

    @abstractmethod
    def call(self, system_prompt: str, user_message: str) -> dict:
        """Send a prompt to the AI and return parsed JSON response.

        Args:
            system_prompt: System instructions (JSON-only output, etc.)
            user_message: The user's actual query

        Returns:
            Parsed JSON dict from the AI response.

        Raises:
            ProviderError: If the API call or response parsing fails.
        """
        pass

    def _parse_json_from_text(self, text: str) -> dict:
        """Extract and parse JSON from text that might contain extras."""
        text = text.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        raise ProviderError(f"Could not parse JSON from AI response: {text[:200]}")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    def call(self, system_prompt: str, user_message: str) -> dict:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message},
            ],
        }
        if self.structured_output:
            payload["tools"] = [{
                "name": "return_json",
                "description": "Return the requested JSON output.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "json_output": {
                            "type": "string",
                            "description": "A JSON string containing the response."
                        }
                    },
                    "required": ["json_output"]
                }
            }]
            payload["tool_choice"] = {"type": "tool", "name": "return_json"}

        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.ConnectionError:
            raise ProviderError("Cannot connect to Anthropic API. Check your internet connection.")
        except requests.Timeout:
            raise ProviderError("Anthropic API request timed out.")

        if response.status_code == 401:
            raise ProviderError("Invalid Anthropic API key. Run 'sapt config --set-key' to update.")
        if response.status_code == 429:
            raise ProviderError("Anthropic API rate limit exceeded. Please wait and try again.")
        if response.status_code != 200:
            raise ProviderError(f"Anthropic API error ({response.status_code}): {response.text[:200]}")

        data = response.json()
        
        # Handle tool call response
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "return_json":
                input_data = block.get("input", {})
                text = input_data.get("json_output", "")
                if text:
                    break
            elif block.get("type") == "text":
                text = block.get("text", "")
                
        if not text:
            raise ProviderError("Empty response from Anthropic API.")

        return self._parse_json_from_text(text)


class OpenAIProvider(BaseProvider):
    """OpenAI API provider (also works with OpenAI-compatible endpoints)."""

    def call(self, system_prompt: str, user_message: str) -> dict:
        headers = {
            "content-type": "application/json",
        }
        if self.api_key and self.api_key != "local":
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,  # Low temperature for deterministic output
        }
        if self.structured_output:
            payload["response_format"] = {"type": "json_object"}

        response = self._post_json(payload, headers)
        if response.status_code == 400 and "response_format" in payload:
            payload.pop("response_format", None)
            response = self._post_json(payload, headers)

        if response.status_code == 401:
            raise ProviderError("Invalid API key. Run 'sapt config --set-key' to update.")
        if response.status_code == 429:
            raise ProviderError("API rate limit exceeded. Please wait and try again.")
        if response.status_code != 200:
            raise ProviderError(f"API error ({response.status_code}): {response.text[:200]}")

        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not text:
            raise ProviderError("Empty response from API.")

        return self._parse_json_from_text(text)

    def _post_json(self, payload: dict, headers: dict) -> requests.Response:
        try:
            return requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.ConnectionError:
            raise ProviderError("Cannot connect to OpenAI API. Check your internet connection.")
        except requests.Timeout:
            raise ProviderError("OpenAI API request timed out.")


class GeminiProvider(BaseProvider):
    """Google Gemini API provider."""

    def call(self, system_prompt: str, user_message: str) -> dict:
        # Gemini uses URL-based auth and a different endpoint structure
        url = f"{self.endpoint}{self.model}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "parts": [{"text": user_message}],
                },
            ],
            "generationConfig": {
                "maxOutputTokens": DEFAULT_MAX_TOKENS,
                "temperature": 0.1,
            },
        }
        if self.structured_output:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
        except requests.ConnectionError:
            raise ProviderError("Cannot connect to Gemini API. Check your internet connection.")
        except requests.Timeout:
            raise ProviderError("Gemini API request timed out.")

        if response.status_code == 400:
            raise ProviderError(f"Invalid Gemini API key or request: {response.text[:200]}")
        if response.status_code == 429:
            raise ProviderError("Gemini API rate limit exceeded. Please wait and try again.")
        if response.status_code != 200:
            raise ProviderError(f"Gemini API error ({response.status_code}): {response.text[:200]}")

        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise ProviderError(f"Unexpected Gemini response format: {json.dumps(data)[:200]}")

        return self._parse_json_from_text(text)


# ── Provider Factory ─────────────────────────────────────────────

_PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider(config: dict) -> BaseProvider:
    """Factory function to get the appropriate provider for a config.

    For custom endpoints, the 'format' field determines which
    provider class to use (openai or anthropic compatible).
    """
    provider_key = config.get("provider", "")
    api_format = config.get("format", "openai")

    # Known provider
    if provider_key in _PROVIDER_MAP:
        return _PROVIDER_MAP[provider_key](config)

    # Custom provider — route by format
    if api_format == "anthropic":
        return AnthropicProvider(config)
    else:
        # Default to OpenAI-compatible (covers most third-party providers)
        return OpenAIProvider(config)
