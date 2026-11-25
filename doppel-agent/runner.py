"""Run scenarios on both systems.

billing-v1 is the reference and never changes, so its outputs are cached per scenario (keyed by the
scenario's fingerprint and a hash of the v1 source). A re-run after a change to billing-v2 only calls v2.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any, AsyncIterator

from backends import Backend
from scenarios import Scenario

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
_REF = re.compile(r"^\$(\w+)\.(\w+)$")


def v1_source_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "billing-v1").glob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _resolve(value: Any, saved: dict[str, Any]) -> Any:
    if isinstance(value, str):
        m = _REF.match(value)
        if m and m.group(1) in saved and isinstance(saved[m.group(1)], dict):
            return saved[m.group(1)].get(m.group(2))
        return value
    if isinstance(value, list):
        return [_resolve(v, saved) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, saved) for k, v in value.items()}
    return value


async def run_steps(backend: Backend, scenario: Scenario, trace: list[dict[str, Any]] | None = None) -> list[Any]:
    """Resets the system, then runs each step. Errors are recorded as outputs, never raised."""
    saved: dict[str, Any] = {}
    outputs: list[Any] = []
    await backend.call("reset", {})
    if trace is not None:
        trace.append({"system": backend.name, "tool": "reset", "args": {}})
    for step in scenario.steps:
        args = _resolve(step.args, saved)
        try:
            out = await backend.call(step.tool, args)
        except Exception as exc:  # a transport failure is a result too
            out = {"error": "exception", "detail": f"{type(exc).__name__}: {exc}"}
        if trace is not None:
            trace.append({"system": backend.name, "tool": step.tool, "args": args})
        outputs.append(out)
        if step.save_as:
            saved[step.save_as] = out
    return outputs


class V1Cache:
    def __init__(self, path: Path | None = None):
        self.path = path or CACHE_DIR / "v1_results.json"
        self.version = v1_source_hash()
        self.data: dict[str, Any] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                if raw.get("version") == self.version:
                    self.data = raw.get("results", {})
            except ValueError:
                pass

    def get(self, scenario: Scenario) -> list[Any] | None:
        return self.data.get(scenario.fingerprint())

    def put(self, scenario: Scenario, outputs: list[Any]) -> None:
        self.data[scenario.fingerprint()] = outputs

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"version": self.version, "results": self.data}))

    def clear(self) -> None:
        self.data = {}
        if self.path.exists():
            self.path.unlink()


async def run_all(
    v1: Backend,
    v2: Backend,
    scenarios: list[Scenario],
    cache: V1Cache | None = None,
    trace: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Yields ``{scenario, v1, v2, v1_cached, trace}`` per scenario, in order.

    Each system has one database, so scenarios run one after another; v1 and v2 run in parallel.
    """
    for sc in scenarios:
        steps_trace: list[dict[str, Any]] | None = [] if trace else None
        cached = cache.get(sc) if cache else None
        if cached is not None:
            v1_out, v2_out = cached, await run_steps(v2, sc, steps_trace)
        else:
            v1_out, v2_out = await asyncio.gather(run_steps(v1, sc, steps_trace), run_steps(v2, sc, steps_trace))
            if cache:
                cache.put(sc, v1_out)
        yield {"scenario": sc, "v1": v1_out, "v2": v2_out, "v1_cached": cached is not None, "trace": steps_trace or []}
    if cache:
        cache.save()
