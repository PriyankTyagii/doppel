"""Grok (xAI) chat completions with schema-constrained JSON output.

Config: XAI_API_KEY (required), XAI_MODEL (default below), XAI_BASE_URL (default https://api.x.ai/v1).
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "grok-4-1-fast"
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


def model_name() -> str:
    return os.environ.get("XAI_MODEL", DEFAULT_MODEL)


def configured() -> bool:
    return bool(os.environ.get("XAI_API_KEY"))


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema made strict: refs inlined, every property required, no extra keys,
    and string constraints xAI rejects (min/max length, pattern) removed."""
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


async def complete_json(system: str, user: str, schema: type[T], *, timeout: float = 120) -> T:
    """One chat completion whose reply must validate against ``schema``."""
    key = os.environ.get("XAI_API_KEY")
    if not key:
        raise LLMError("XAI_API_KEY is not set")
    body = {
        "model": model_name(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": strict_schema(schema), "strict": True},
        },
    }
    base = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base}/chat/completions", json=body,
                                     headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        raise LLMError(f"could not reach xAI: {exc}") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error") or resp.text
        except ValueError:
            detail = resp.text
        raise LLMError(f"xAI returned {resp.status_code}: {str(detail)[:300]}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        return schema.model_validate(json.loads(content))
    except (KeyError, IndexError, ValueError, ValidationError) as exc:
        raise LLMError(f"unexpected reply from xAI: {exc}") from exc
