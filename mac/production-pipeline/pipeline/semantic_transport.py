"""Opt-in OpenAI-compatible transport for external LLM gateways.

No credentials embedded in repository or logged into job artifacts.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request


class ProviderUnavailable(RuntimeError):
    pass


def configured() -> bool:
    if os.getenv("Y700_LLM_BACKEND", "codex").lower() == "codex":
        from shutil import which
        return which("codex") is not None
    return bool(os.getenv("Y700_LLM_BASE_URL") and os.getenv("Y700_LLM_MODEL"))


def invoke_codex(payload: dict, *, role: str, timeout: int = 180) -> dict:
    """Use the locally authenticated Codex CLI; never copy OAuth credentials."""
    system = ("Independently audit Chinese-to-Burmese translations; evaluate omissions, "
              "negations, numbers, technical terms and meaning. Return every requested "
              "event_id with a pass/fail/uncertain verdict and a reason."
              if role == "audit" else
              ("Translate every target Chinese event faithfully into Burmese; preserve "
               "event_id and return ONLY the required translations JSON."
               if role == "translate" else
               "Correct ONLY the flagged Chinese-to-Burmese event translations. "
               "Preserve each event_id; return translations as JSON."))
    prompt = system + "\nReturn one JSON object and no markdown.\n" + json.dumps(payload, ensure_ascii=False)
    model = os.getenv("Y700_CODEX_AUDIT_MODEL" if role == "audit" else "Y700_CODEX_MODEL", "").strip()
    with tempfile.TemporaryDirectory(prefix="y700-llm-") as workdir:
        output_file = os.path.join(workdir, "last-message.json")
        args = ["codex", "exec", "--output-last-message", output_file,
                "--cd", workdir, "--sandbox", "read-only",
                "--skip-git-repo-check", "--ephemeral", "--color", "never"]
        if model:
            args.extend(["--model", model])
        args.append("-")
        try:
            completed = subprocess.run(args, input=prompt, capture_output=True, text=True,
                                       cwd=workdir, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProviderUnavailable("Codex CLI unavailable or timed out") from exc
        if completed.returncode:
            raise ProviderUnavailable("Codex CLI exited with status " + str(completed.returncode))
        try:
            with open(output_file, encoding="utf-8") as result_file:
                answer = json.load(result_file)
        except (OSError, ValueError, TypeError) as exc:
            raise ProviderUnavailable("Codex CLI last response is not valid JSON") from exc
        if not isinstance(answer, dict):
            raise ProviderUnavailable("Codex CLI response is not an object")
        return answer


def invoke_json(payload: dict, *, role: str, timeout: int = 90) -> dict:
    """Codex CLI is the default LLM backend for the subtitle pipeline."""
    backend = os.getenv("Y700_LLM_BACKEND", "codex").lower()
    if backend == "codex":
        return invoke_codex(payload, role=role, timeout=max(timeout, 180))
    if backend != "gateway":
        raise ProviderUnavailable("unsupported LLM backend")
    base = os.getenv("Y700_LLM_BASE_URL", "").rstrip("/")
    model = os.getenv("Y700_LLM_AUDIT_MODEL" if role == "audit" else
                      "Y700_LLM_MODEL") or os.getenv("Y700_LLM_MODEL", "")
    token = os.getenv("Y700_LLM_API_KEY", "")
    if not base or not model:
        raise ProviderUnavailable("LLM gateway URL/model not configured")
    if not base.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
        raise ProviderUnavailable("refuse insecure remote LLM transport")
    if not token:
        raise ProviderUnavailable("LLM credential missing")
    url = base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
    body = json.dumps({
        "model": model, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "You are an independent source-faithful translation reviewer."
                if role == "audit" else
                "You translate Chinese into Burmese faithfully. Return JSON only."
            )},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }, ensure_ascii=False).encode()
    request = urllib.request.Request(url, body, {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            result = json.load(reply)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise ProviderUnavailable("LLM gateway call failed: " + type(exc).__name__) from exc
    try:
        return json.loads(result["choices"][0]["message"]["content"])
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ProviderUnavailable("LLM gateway returned non-JSON response") from exc
