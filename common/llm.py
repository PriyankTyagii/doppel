"""Groq chat completions (OpenAI-compatible API) with schema-constrained JSON output.

Config: GROQ_API_KEY (required), GROQ_MODEL (default below), GROQ_BASE_URL (default https://api.groq.com/openai/v1).
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "openai/gpt-oss-120b"
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


def model_name() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


def configured() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema made strict: refs inlined, every property required, no extra keys,
    and string constraints strict mode rejects (min/max length, pattern) removed."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            node = {k: walk(v) for k, v in node.items()
                    if k not in ("title", "default", "minLength", "maxLength", "pattern")}
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


MAX_RATE_LIMIT_WAIT_S = 60


async def complete_json(system: str, user: str, schema: type[T], *, max_tokens: int = 2000,
                        reasoning_effort: str = "low", timeout: float = 120) -> T:
    """One chat completion whose reply must validate against ``schema``.

    On a 429 (the free tier allows a few thousand tokens per minute) it waits for the time Groq asks,
    up to MAX_RATE_LIMIT_WAIT_S, and retries once.
    """
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY is not set")
    body = {
        "model": model_name(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": strict_schema(schema), "strict": True},
        },
        "max_completion_tokens": max_tokens,
    }
    if model_name().startswith("openai/gpt-oss"):
        body["reasoning_effort"] = reasoning_effort
    base = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(2):
                resp = await client.post(f"{base}/chat/completions", json=body,
                                         headers={"Authorization": f"Bearer {key}"})
                wait = _retry_after(resp)
                if resp.status_code != 429 or attempt or wait > MAX_RATE_LIMIT_WAIT_S:
                    break
                await asyncio.sleep(wait)
    except httpx.HTTPError as exc:
        raise LLMError(f"could not reach Groq: {exc}") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error") or resp.text
        except ValueError:
            detail = resp.text
        raise LLMError(f"Groq returned {resp.status_code}: {str(detail)[:300]}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        return schema.model_validate(json.loads(content))
    except (KeyError, IndexError, ValueError, ValidationError) as exc:
        raise LLMError(f"unexpected reply from Groq: {exc}") from exc


def _retry_after(resp: httpx.Response) -> float:
    try:
        return float(resp.headers.get("retry-after", "5"))
    except ValueError:
        return 5.0
