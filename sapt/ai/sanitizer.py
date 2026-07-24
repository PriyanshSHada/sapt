"""
sapt.ai.sanitizer
Input sanitization and prompt injection defense (Layer 1 security).
Also validates AI response JSON against expected schema.
"""

import re
import json

from sapt.utils.constants import (
    MAX_INPUT_LEN,
    VALID_SOURCES,
    VALID_PKG_NAME_PATTERN,
)

# ── Suspicious Patterns (prompt injection attempts) ──────────────
SUSPICIOUS_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"forget\s+(all\s+)?(previous|prior|above)",
    r"you\s+are\s+now",
    r"new\s+instructions",
    r"system\s*prompt",
    r"override\s+instructions",
    r"act\s+as\s+(a\s+)?",
    r"pretend\s+to\s+be",
    r"execute\s+command",
    r"run\s+command",
    r"```",  # Code fence attempts
    r"---\s*\n",  # Markdown separator attempts
    r"\{\{",  # Template injection
    r"<script",  # XSS-style injection
    r";\s*rm\s",  # Shell command injection
    r"&&\s*rm\s",
    r"\|\s*bash",
    r"curl\s.*\|\s*sh",
]

# Compile patterns for performance
_COMPILED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in SUSPICIOUS_PATTERNS
]


class SanitizationError(Exception):
    """Raised when input fails sanitization checks."""

    pass


class InvalidAIResponseError(Exception):
    """Raised when AI response doesn't match expected schema."""

    pass


class InputSanitizer:
    """Sanitize user input before sending to AI layer."""

    def check(self, user_input: str) -> str:
        """Validate and clean user input.

        Returns cleaned input string.
        Raises SanitizationError if input is suspicious.
        """
        if not user_input or not user_input.strip():
            raise SanitizationError("Empty input.")

        cleaned = user_input.strip()

        # Length check
        if len(cleaned) > MAX_INPUT_LEN:
            raise SanitizationError(
                f"Input too long ({len(cleaned)} chars, max {MAX_INPUT_LEN}). "
                f"Package names should be short."
            )

        # Control character check
        if any(ord(c) < 32 and c not in ("\n", "\t") for c in cleaned):
            raise SanitizationError("Input contains invalid control characters.")

        # Prompt injection pattern check
        for pattern in _COMPILED_PATTERNS:
            if pattern.search(cleaned):
                raise SanitizationError(
                    "Input contains suspicious patterns and was rejected for safety. "
                    "If this is a legitimate package name, please file a bug report."
                )

        return cleaned

    def check_package_name(self, package_name: str) -> str:
        """Validate a resolved package name (from AI response).

        Returns the validated name.
        Raises SanitizationError if the name is invalid.
        """
        if not package_name or not package_name.strip():
            raise SanitizationError("Empty package name from AI response.")

        name = package_name.strip().lower()

        if not re.match(VALID_PKG_NAME_PATTERN, name):
            raise SanitizationError(
                f"Invalid package name '{name}'. "
                f"Package names must match pattern: {VALID_PKG_NAME_PATTERN}"
            )

        return name


def validate_ai_response(raw_response: str) -> dict:
    """Parse and validate an AI response against the expected schema.

    Expected schema:
    {
        "package": str,       # Required — exact package name
        "source": str,        # Required — one of VALID_SOURCES
        "confidence": float,  # Required — 0.0 to 1.0
        "alternatives": list, # Optional — list of strings
        "notes": str          # Optional — post-install tips
    }

    Returns the validated dict.
    Raises InvalidAIResponseError on any schema violation.
    """
    # Strip markdown code fences if AI wrapped the JSON
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        # Remove ```json ... ``` wrapping
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Parse JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise InvalidAIResponseError(
            f"AI response is not valid JSON: {e}\nRaw: {raw_response[:200]}"
        )

    if not isinstance(data, dict):
        raise InvalidAIResponseError("AI response must be a JSON object.")

    # Validate required fields
    if "package" not in data:
        raise InvalidAIResponseError("AI response missing 'package' field.")

    if "source" not in data:
        raise InvalidAIResponseError("AI response missing 'source' field.")

    if "confidence" not in data:
        raise InvalidAIResponseError("AI response missing 'confidence' field.")

    # Validate field types and values
    if not isinstance(data["package"], str) or not data["package"].strip():
        raise InvalidAIResponseError("'package' must be a non-empty string.")

    if data["source"] not in VALID_SOURCES:
        raise InvalidAIResponseError(
            f"'source' must be one of {VALID_SOURCES}, got '{data['source']}'."
        )

    try:
        data["confidence"] = float(data["confidence"])
    except (TypeError, ValueError):
        raise InvalidAIResponseError("'confidence' must be a number.")

    if not (0.0 <= data["confidence"] <= 1.0):
        raise InvalidAIResponseError("'confidence' must be between 0.0 and 1.0.")

    # Validate optional fields
    if "alternatives" in data:
        if not isinstance(data["alternatives"], list):
            data["alternatives"] = []
        data["alternatives"] = [
            str(a).strip() for a in data["alternatives"] if str(a).strip()
        ][
            :5
        ]  # Max 5 alternatives
    else:
        data["alternatives"] = []

    if "notes" not in data:
        data["notes"] = ""
    else:
        data["notes"] = str(data["notes"])

    # Validate the AI-provided package name here as well as immediately before
    # execution.  Keeping the boundary strict prevents unsafe values entering
    # caches, UI output, or a later execution path.
    try:
        data["package"] = InputSanitizer().check_package_name(data["package"])
    except SanitizationError as e:
        raise InvalidAIResponseError(str(e)) from e

    return data
