"""How Doppel talks to a billing system.

Every scenario step is a *logical* tool call such as ``create_invoice``. A backend turns that into a
real call: ``HttpBackend`` hits the REST API directly (for development before Synapse is set up),
``McpBackend`` calls the tool on that system's Synapse MCP server (the real path for the demo).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

LOGICAL_TOOLS: dict[str, tuple[str, str]] = {
    "reset": ("POST", "/reset"),
    "create_customer": ("POST", "/customers"),
    "create_invoice": ("POST", "/invoices"),
    "get_invoice": ("GET", "/invoices/{id}"),
    "pay_invoice": ("POST", "/invoices/{id}/pay"),
    "refund_invoice": ("POST", "/invoices/{id}/refund"),
    # Added during the live demo, after `synapse build --discover`.
    "get_invoice_breakdown": ("GET", "/invoices/{id}/breakdown"),
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "reset": "Reload deterministic seed data (10 customers, 15 products). No arguments.",
    "create_customer": "Create a customer. Args: name (str), state (Indian state name).",
    "create_invoice": (
        "Create an invoice. Args: customer_id (int), items (list of {sku, qty, unit_price?, gst_rate?}), "
        "coupon_pct (int, optional), due_date (YYYY-MM-DD)."
    ),
    "get_invoice": "Fetch an invoice. Args: id (int).",
    "pay_invoice": "Pay an invoice; a late fee may apply. Args: id (int), paid_on (YYYY-MM-DD).",
    "refund_invoice": "Refund part of an invoice. Args: id (int), sku (str), qty (int).",
}


class Backend(Protocol):
    name: str

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def reconnect(self) -> list[str]: ...
    async def call(self, tool: str, args: dict[str, Any]) -> Any: ...
    def tool_names(self) -> list[str]: ...


def _split_path_args(path: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    body = dict(args)
    for key in re.findall(r"{(\w+)}", path):
        path = path.replace("{" + key + "}", str(body.pop(key)))
    return path, body


class HttpBackend:
    """Calls a billing system's REST API directly."""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=15)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def reconnect(self) -> list[str]:
        await self.close()
        await self.connect()
        return self.tool_names()

    def tool_names(self) -> list[str]:
        return [t for t in LOGICAL_TOOLS if t != "get_invoice_breakdown"]

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        assert self._client, "backend not connected"
        method, path = LOGICAL_TOOLS[tool]
        path, body = _split_path_args(path, args)
        if method == "GET":
            resp = await self._client.get(path)
        else:
            resp = await self._client.request(method, path, json=body)
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text}
        if resp.status_code >= 400:
            return {"error": resp.status_code, "detail": payload.get("detail") if isinstance(payload, dict) else payload}
        return payload


@dataclass
class McpServerConfig:
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # Optional explicit map from logical tool -> MCP tool name, for when the heuristic guesses wrong.
    tools: dict[str, str] = field(default_factory=dict)


_ENV_REF = re.compile(r"\$\{(\w+)\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def load_mcp_config(path: str | Path) -> dict[str, McpServerConfig]:
    """Reads a desktop-client-style mcp.json (``mcpServers``). ``${ENV}`` placeholders are expanded from the environment."""
    raw = json.loads(Path(path).read_text())
    servers = raw.get("mcpServers", raw)
    out: dict[str, McpServerConfig] = {}
    for name, cfg in servers.items():
        cfg = _expand(cfg)
        out[name] = McpServerConfig(
            command=cfg.get("command"),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
            url=cfg.get("url"),
            headers=cfg.get("headers", {}),
            tools=cfg.get("doppel_tools", {}),
        )
    return out


# Words that identify each logical tool in a generated MCP tool name/description.
_TOOL_HINTS: dict[str, list[list[str]]] = {
    "reset": [["reset"]],
    "create_customer": [["customer"]],
    "get_invoice_breakdown": [["breakdown"]],
    "pay_invoice": [["pay"]],
    "refund_invoice": [["refund"]],
    "create_invoice": [["create", "invoice"], ["post", "invoices"], ["new", "invoice"], ["add", "invoice"]],
    "get_invoice": [["get", "invoice"], ["fetch", "invoice"], ["read", "invoice"], ["retrieve", "invoice"]],
}


def resolve_tools(mcp_tools: list[Any], overrides: dict[str, str]) -> dict[str, Any]:
    """Maps logical tool names to the MCP tools a Synapse build exposes.

    Synapse picks tool names itself (``--smart-names``), so match on name words, then description.
    Explicit ``doppel_tools`` overrides in mcp.json always win.
    """
    by_name = {t.name: t for t in mcp_tools}
    resolved: dict[str, Any] = {}
    for logical, mcp_name in overrides.items():
        if mcp_name in by_name:
            resolved[logical] = by_name[mcp_name]

    def words(text: str) -> set[str]:
        return set(re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "").lower()))

    taken = {t.name for t in resolved.values()}
    # Most specific first so "pay" and "refund" are claimed before the generic invoice tools.
    for logical in ["reset", "create_customer", "get_invoice_breakdown", "pay_invoice", "refund_invoice",
                    "create_invoice", "get_invoice"]:
        if logical in resolved:
            continue
        for tool in mcp_tools:
            if tool.name in taken:
                continue
            name_words = words(tool.name)
            desc_words = words(tool.description or "")
            if any(all(w in name_words or w + "s" in name_words for w in hint) for hint in _TOOL_HINTS[logical]) or (
                logical in ("get_invoice", "create_invoice")
                and any(all(w in desc_words for w in hint) for hint in _TOOL_HINTS[logical])
                and not ({"pay", "refund", "breakdown", "customer", "reset"} & name_words)
            ):
                resolved[logical] = tool
                taken.add(tool.name)
                break
    return resolved


def _shape_args(tool: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Fits flat logical args into the tool's input schema (flat, or path params + a ``body`` object)."""
    props = (tool.input_schema or {}).get("properties", {})
    if "body" in props:
        body = {k: v for k, v in args.items() if k not in props or k == "body"}
        top = {k: v for k, v in args.items() if k in props and k != "body"}
        if "id" in args and "id" not in props:
            for alt in ("invoice_id", "invoiceId"):
                if alt in props:
                    top[alt] = body.pop("id")
        if body:
            top["body"] = body
        return top
    shaped = dict(args)
    if "id" in shaped and "id" not in props:
        for alt in ("invoice_id", "invoiceId"):
            if alt in props:
                shaped[alt] = shaped.pop("id")
    return shaped


def _parse_result(result: Any) -> Any:
    if result.structured_content is not None:
        payload: Any = result.structured_content
    else:
        texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        joined = "\n".join(texts)
        try:
            payload = json.loads(joined)
        except ValueError:
            payload = {"raw": joined}
    if result.is_error:
        detail = payload.get("detail") if isinstance(payload, dict) else payload
        status = payload.get("status", payload.get("error", "tool_error")) if isinstance(payload, dict) else "tool_error"
        return {"error": status, "detail": detail}
    return payload


class McpBackend:
    """Calls one billing system through its Synapse MCP server."""

    def __init__(self, name: str, config: McpServerConfig):
        self.name = name
        self.config = config
        self._client: Any = None
        self._tools: dict[str, Any] = {}
        self.raw_tool_names: list[str] = []

    async def connect(self) -> None:
        from mcp import Client, StdioServerParameters

        if self.config.url and self.config.headers:
            import httpx2  # the MCP SDK's HTTP client
            from mcp.client.streamable_http import streamable_http_client

            http = httpx2.AsyncClient(headers=self.config.headers, timeout=60)
            target: Any = streamable_http_client(self.config.url, http_client=http)
        elif self.config.url:
            target = self.config.url
        else:
            target = StdioServerParameters(command=self.config.command, args=self.config.args, env=self.config.env)
        self._client = Client(target)
        await self._client.__aenter__()
        await self._refresh_tools()

    async def _refresh_tools(self) -> None:
        listed = await self._client.list_tools(cache_mode="refresh")
        self.raw_tool_names = [t.name for t in listed.tools]
        self._tools = resolve_tools(listed.tools, self.config.tools)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            finally:
                self._client = None

    async def reconnect(self) -> list[str]:
        """Closes and reopens the session, then re-lists tools (needed after `synapse build --discover`)."""
        await self.close()
        await self.connect()
        return self.tool_names()

    def tool_names(self) -> list[str]:
        return list(self._tools)

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        if tool not in self._tools:
            return {"error": "missing_tool", "detail": f"{self.name} exposes no tool for {tool}"}
        mcp_tool = self._tools[tool]
        result = await self._client.call_tool(mcp_tool.name, _shape_args(mcp_tool, args))
        return _parse_result(result)


def make_backends(mode: str, mcp_config_path: str | None = None) -> tuple[Backend, Backend]:
    if mode == "http":
        return (
            HttpBackend("billing_v1", os.environ.get("BILLING_V1_URL", "http://localhost:8001")),
            HttpBackend("billing_v2", os.environ.get("BILLING_V2_URL", "http://localhost:8002")),
        )
    servers = load_mcp_config(mcp_config_path or Path(__file__).with_name("mcp.json"))
    return McpBackend("billing_v1", servers["billing_v1"]), McpBackend("billing_v2", servers["billing_v2"])
