"""
Kiro CLI client for programmatic LLM access.

Uses `kiro-cli chat --no-interactive --wrap=never --agent analyzer`
for clean, structured inference. Strips the minimal ANSI prefix that
kiro-cli emits even with --wrap=never.

Design: one subprocess per prompt (session/new in ACP is broken in
kiro-cli 2.13.0). This is still much better than the old approach
because the custom `analyzer` agent provides a proper system prompt
and disables tools/MCP, making responses faster and more predictable.
"""
import json
import logging
import re
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ANSI escape sequence pattern
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class KiroCLIClient:
    """
    Clean kiro-cli --no-interactive wrapper.

    Usage:
        client = KiroCLIClient(effort="low")
        result = client.prompt("Summarize this article...")
        json_result = client.prompt_json("Return JSON: ...")
    """

    def __init__(
        self,
        effort: str = "low",
        agent: str = "analyzer",
        model: Optional[str] = None,
        timeout: int = 300,
        cwd: Optional[str] = None,
    ):
        self.effort = effort
        self.agent = agent
        self.model = model
        self.timeout = timeout
        self.cwd = cwd

    def check_connection(self) -> bool:
        """Check if kiro-cli is available."""
        try:
            result = subprocess.run(
                ["kiro-cli", "--version"], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def prompt(self, message: str, timeout: Optional[int] = None) -> str:
        """
        Send a prompt and get the text response.

        Args:
            message: The prompt text.
            timeout: Override default timeout in seconds.

        Returns:
            Clean text response (ANSI stripped).
        """
        cmd = ["kiro-cli", "chat", "--no-interactive", "--wrap=never"]
        if self.agent:
            cmd.extend(["--agent", self.agent])
        if self.effort:
            cmd.extend(["--effort", self.effort])
        if self.model:
            cmd.extend(["--model", self.model])

        effective_timeout = timeout or self.timeout

        try:
            logger.info("⏳ Calling kiro-cli (timeout=%ds)...", effective_timeout)
            result = subprocess.run(
                cmd,
                input=message,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                cwd=self.cwd,
            )

            if result.returncode != 0:
                logger.error("kiro-cli error (rc=%d): %s", result.returncode, result.stderr[:200])
                return ""

            # Strip ANSI codes and the "> " prefix kiro adds
            clean = _ANSI_RE.sub("", result.stdout)
            # Remove leading "> " prompt marker if present
            clean = re.sub(r"^>\s*", "", clean, count=1)
            clean = clean.strip()

            logger.info("✓ Response received (%d chars)", len(clean))
            return clean

        except subprocess.TimeoutExpired:
            logger.error("kiro-cli timed out after %ds", effective_timeout)
            return ""
        except Exception as exc:
            logger.error("kiro-cli call failed: %s", exc)
            return ""

    def prompt_json(self, message: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Send a prompt expecting a JSON response.

        Args:
            message: The prompt (should instruct model to return JSON only).
            timeout: Override default timeout.

        Returns:
            Parsed JSON dict, or empty dict on failure.
        """
        text = self.prompt(message, timeout=timeout)
        if not text:
            return {}
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extract the first valid JSON object from text."""
        text = text.strip()

        # Try whole text as JSON
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try inside markdown code blocks
        block_match = re.search(r"```(?:json)?\s*\n?({.*?})\s*\n?```", text, re.DOTALL)
        if block_match:
            try:
                return json.loads(block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Find first { ... } block (handles nested objects)
        depth = 0
        start = None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        start = None

        logger.error("No valid JSON found in response (%d chars)", len(text))
        return {}
