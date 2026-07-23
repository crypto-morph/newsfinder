"""
ACP (Agent Client Protocol) client for kiro-cli.

Manages a persistent kiro-cli acp subprocess, communicates via JSON-RPC 2.0
over stdin/stdout. Reuses a single session for multiple prompts — no subprocess
spawn per call.
"""
import json
import logging
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ACPClient:
    """
    Persistent ACP connection to kiro-cli.

    Usage:
        client = ACPClient(model="anthropic.claude-sonnet-4-20250514", effort="low")
        client.start()
        result = client.prompt("Summarize this article: ...")
        json_result = client.prompt_json("Return JSON: {\"score\": 5}")
        client.stop()

    Or as a context manager:
        with ACPClient() as client:
            result = client.prompt("hello")
    """

    def __init__(
        self,
        model: Optional[str] = None,
        effort: str = "low",
        agent: Optional[str] = None,
        trust_all_tools: bool = False,
        system_prompt: Optional[str] = None,
    ):
        self.model = model
        self.effort = effort
        self.agent = agent
        self.trust_all_tools = trust_all_tools
        self.system_prompt = system_prompt

        self._process: Optional[subprocess.Popen] = None
        self._session_id: Optional[str] = None
        self._request_id: int = 0
        self._lock = threading.Lock()
        self._started = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn kiro-cli acp subprocess and initialize the session."""
        if self._started:
            return

        cmd = ["kiro-cli", "acp"]
        if self.model:
            cmd.extend(["--model", self.model])
        if self.effort:
            cmd.extend(["--effort", self.effort])
        if self.agent:
            cmd.extend(["--agent", self.agent])
        if self.trust_all_tools:
            cmd.append("--trust-all-tools")

        logger.info("Starting ACP subprocess: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )

        # Initialize the connection
        self._initialize()

        # Create a session
        self._create_session()

        self._started = True
        logger.info("ACP client ready (session=%s)", self._session_id)

    def stop(self) -> None:
        """Terminate the ACP subprocess."""
        if self._process:
            try:
                self._process.stdin.close()
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            finally:
                self._process = None
                self._started = False
                self._session_id = None
                logger.info("ACP subprocess stopped")

    @property
    def is_alive(self) -> bool:
        """Check if the subprocess is still running."""
        return self._process is not None and self._process.poll() is None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prompt(self, message: str, timeout: int = 300) -> str:
        """
        Send a prompt and collect the full text response.

        Args:
            message: The prompt text to send.
            timeout: Max seconds to wait for response.

        Returns:
            The agent's text response.
        """
        self._ensure_alive()
        return self._send_prompt(message, timeout=timeout)

    def prompt_json(self, message: str, timeout: int = 300) -> Dict[str, Any]:
        """
        Send a prompt expecting a JSON response.

        Extracts the first valid JSON object from the response text.

        Args:
            message: The prompt text (should instruct model to return JSON).
            timeout: Max seconds to wait.

        Returns:
            Parsed JSON dict, or empty dict on failure.
        """
        text = self.prompt(message, timeout=timeout)
        return self._extract_json(text)

    # ------------------------------------------------------------------
    # JSON-RPC transport
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Send a JSON-RPC request and return the response."""
        msg = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            msg["params"] = params

        line = json.dumps(msg) + "\n"
        logger.debug("ACP TX: %s", line.strip())

        with self._lock:
            self._process.stdin.write(line)
            self._process.stdin.flush()

        return msg["id"]

    def _read_message(self, timeout: int = 60) -> Optional[Dict]:
        """Read a single JSON-RPC message from stdout."""
        # Simple line-based read with timeout via select/poll would be ideal,
        # but for now use blocking reads (kiro-cli responds promptly).
        line = self._process.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        try:
            msg = json.loads(line)
            logger.debug("ACP RX: %s", line[:200])
            return msg
        except json.JSONDecodeError:
            logger.warning("ACP: non-JSON line: %s", line[:100])
            return None

    def _wait_for_response(self, request_id: int, timeout: int = 60) -> Dict:
        """Wait for a JSON-RPC response matching the given request ID."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self._read_message(timeout=timeout)
            if msg is None:
                if not self.is_alive:
                    raise RuntimeError("ACP process died unexpectedly")
                continue
            # Match response by ID
            if msg.get("id") == request_id:
                if "error" in msg:
                    raise RuntimeError(
                        f"ACP error: {msg['error'].get('message', msg['error'])}"
                    )
                return msg.get("result", {})
            # Otherwise it's a notification — ignore for now
        raise TimeoutError(f"ACP: no response for request {request_id} within {timeout}s")

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Send the ACP initialize handshake."""
        req_id = self._send_request("initialize", {
            "protocolVersion": "2025-01-01",
            "clientInfo": {
                "name": "newsfinder",
                "version": "1.0.0",
            },
            "capabilities": {},
        })
        result = self._wait_for_response(req_id, timeout=30)
        logger.info("ACP initialized: %s", result.get("serverInfo", {}).get("name", "unknown"))

    def _create_session(self) -> None:
        """Create a new ACP session."""
        params: Dict[str, Any] = {}
        if self.system_prompt:
            params["systemPrompt"] = self.system_prompt

        req_id = self._send_request("session/new", params)
        result = self._wait_for_response(req_id, timeout=30)
        self._session_id = result.get("sessionId", result.get("id", "unknown"))

    def _send_prompt(self, message: str, timeout: int = 300) -> str:
        """
        Send session/prompt and collect all AgentMessageChunk text until TurnEnd.
        """
        req_id = self._send_request("session/prompt", {
            "sessionId": self._session_id,
            "content": [{"type": "text", "text": message}],
        })

        # Collect streaming response chunks
        chunks: List[str] = []
        deadline = time.time() + timeout

        while time.time() < deadline:
            msg = self._read_message(timeout=timeout)
            if msg is None:
                if not self.is_alive:
                    raise RuntimeError("ACP process died during prompt")
                continue

            # Response to the prompt request (acknowledgement)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"ACP prompt error: {msg['error']}")
                # Some implementations send an immediate ack; continue reading
                continue

            # Notifications (streaming content)
            method = msg.get("method", "")
            params = msg.get("params", {})

            if method == "session/notification":
                update_type = params.get("type", "")
                data = params.get("data", {})

                if update_type == "AgentMessageChunk":
                    # Text chunk
                    text = data.get("text", "")
                    if text:
                        chunks.append(text)

                elif update_type == "TurnEnd":
                    # Done
                    break

                elif update_type == "ToolCall":
                    # Agent is using a tool — wait for it to finish
                    logger.debug("ACP tool call: %s", data.get("name", "unknown"))

                # Ignore other notification types

        return "".join(chunks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_alive(self) -> None:
        """Restart the subprocess if it died."""
        if not self.is_alive:
            logger.warning("ACP process not alive, restarting...")
            self._started = False
            self.start()

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extract the first JSON object from text."""
        import re

        # Try the whole text first
        text = text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try to find JSON in markdown code blocks
        block_match = re.search(r"```(?:json)?\s*\n?({.*?})\s*\n?```", text, re.DOTALL)
        if block_match:
            try:
                return json.loads(block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Find first { ... } block
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.error("No valid JSON found in response (%d chars)", len(text))
        return {}
