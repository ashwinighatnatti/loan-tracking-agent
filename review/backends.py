"""Model backends. Anything that can turn (system, user) into text works, so the model is replaceable
and a second model family can review code written by the first (REVIEW.md, model inversion)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .prompt import SHORT_SYSTEM


class BackendError(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


class Backend(Protocol):
    name: str

    def complete(self, system: str, user: str, model: str | None) -> Completion: ...


def _find_claude() -> str:
    explicit = os.environ.get("REVIEW_CLAUDE_BIN")
    if explicit:
        return explicit
    found = shutil.which("claude")
    if not found:
        raise BackendError("claude CLI not found on PATH (set REVIEW_CLAUDE_BIN or pick another --backend)")
    # npm installs shims (.cmd/.ps1) that mangle empty arguments; use the real binary when it is next to them.
    real = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(real) if real.is_file() else found


class ClaudeCli:
    """`claude -p` with every tool disabled, run from an empty directory so that no project settings,
    memory or subagents leak in. The whole rubric travels on stdin (command lines are length-limited)."""
    name = "claude-cli"

    def __init__(self, timeout: int = 900):
        self.timeout = timeout

    def complete(self, system: str, user: str, model: str | None) -> Completion:
        sandbox = Path(tempfile.gettempdir()) / "review-sandbox"
        sandbox.mkdir(exist_ok=True)
        cmd = [_find_claude(), "-p", "--tools", "", "--no-session-persistence", "--disable-slash-commands",
               "--setting-sources", "user", "--output-format", "json", "--system-prompt", SHORT_SYSTEM]
        if model:
            cmd += ["--model", model]
        try:
            proc = subprocess.run(cmd, input=f"{system}\n\n{user}", capture_output=True, text=True,
                                  encoding="utf-8", timeout=self.timeout, cwd=sandbox)
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"claude CLI timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            raise BackendError(f"claude CLI exit {proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise BackendError(f"claude CLI returned non-JSON: {proc.stdout[:200]!r}") from exc
        if data.get("is_error"):
            raise BackendError(f"claude CLI error: {str(data.get('result'))[:400]}")
        usage = data.get("usage", {})
        return Completion(
            text=data.get("result", ""), cost_usd=float(data.get("total_cost_usd", 0) or 0),
            input_tokens=sum(int(usage.get(k, 0) or 0) for k in
                             ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            output_tokens=int(usage.get("output_tokens", 0) or 0))


class AnthropicApi:
    """Direct API. Needs `pip install anthropic` and ANTHROPIC_API_KEY. Cost is not computed
    (token counts only) because prices are not hard-coded here."""
    name = "anthropic"

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str, model: str | None) -> Completion:
        try:
            import anthropic
        except ImportError as exc:
            raise BackendError("pip install anthropic to use the anthropic backend") from exc
        try:
            msg = anthropic.Anthropic().messages.create(
                model=model or "claude-sonnet-5-5", max_tokens=self.max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
        except Exception as exc:  # SDK raises many types; surface them uniformly
            raise BackendError(f"{type(exc).__name__}: {exc}") from exc
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return Completion(text, 0.0, msg.usage.input_tokens, msg.usage.output_tokens)


class CommandBackend:
    """Any other model: a shell command that reads {"system","user","model"} JSON on stdin and prints
    either the reply text or {"text": ..., "cost_usd": ...} on stdout."""
    name = "command"

    def __init__(self, command: str, timeout: int = 900):
        self.command, self.timeout = command, timeout

    def complete(self, system: str, user: str, model: str | None) -> Completion:
        try:
            proc = subprocess.run(self.command, shell=True, input=json.dumps(
                {"system": system, "user": user, "model": model}), capture_output=True, text=True,
                encoding="utf-8", timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"command timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            raise BackendError(f"command exit {proc.returncode}: {proc.stderr[-400:]}")
        out = proc.stdout.strip()
        try:
            data = json.loads(out)
            if isinstance(data, dict) and "text" in data:
                return Completion(str(data["text"]), float(data.get("cost_usd", 0) or 0),
                                  int(data.get("input_tokens", 0) or 0), int(data.get("output_tokens", 0) or 0))
        except json.JSONDecodeError:
            pass
        return Completion(out)


def get(spec: str) -> Backend:
    if spec == "claude-cli":
        return ClaudeCli()
    if spec == "anthropic":
        return AnthropicApi()
    if spec.startswith("command:"):
        return CommandBackend(spec[len("command:"):])
    raise BackendError(f"unknown backend {spec!r}; use claude-cli, anthropic or command:<shell command>")
