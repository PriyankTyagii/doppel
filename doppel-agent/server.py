"""Doppel agent API for the dashboard.

POST /run       stream a parity run (server-sent events)
POST /adhoc     run a judge's plain-English scenario on both systems
GET  /report.md the latest run as a Markdown report
POST /reconnect reopen both MCP sessions and re-list tools (after `synapse build --discover`)

Run: ../.venv/bin/uvicorn server:app --port 8000   (from doppel-agent/)
Mode: DOPPEL_MODE=mcp (default when mcp.json exists) or http.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

import _paths  # noqa: F401
import llm
from firebase_auth import User, allowed_origins, check_config, require_user

from adhoc import plan_scenario
from backends import make_backends
from compare import compare_outputs, impact
from explain import explain_groups, v2_diff_since
from pipeline import DEFAULT_MONTHLY_VOLUME, clear_history, load_run, run_parity, signature, slim_run
from report import render_markdown
from runner import V1Cache, run_steps

MCP_JSON = Path(__file__).with_name("mcp.json")
MODE = os.environ.get("DOPPEL_MODE") or ("mcp" if MCP_JSON.exists() else "http")


class State:
    v1: Any = None
    v2: Any = None
    lock = asyncio.Lock()


S = State()


async def _connect() -> None:
    S.v1, S.v2 = make_backends(MODE, str(MCP_JSON))
    await S.v1.connect()
    await S.v2.connect()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_config()
    await _connect()
    yield
    for b in (S.v1, S.v2):
        if b:
            await b.close()


app = FastAPI(title="Doppel agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/me")
def me(user: User = Depends(require_user)):
    return {"email": user.email, "email_verified": user.email_verified, "is_admin": user.is_admin,
            "mode": MODE, "llm": {"provider": "xAI", "model": llm.model_name(), "configured": llm.configured()},
            "tools": {"billing_v1": S.v1.tool_names(), "billing_v2": S.v2.tool_names()}}


@app.post("/reconnect", dependencies=[Depends(require_user)])
async def reconnect():
    async with S.lock:
        t1 = await S.v1.reconnect()
        t2 = await S.v2.reconnect()
    return {"ok": True, "mode": MODE, "tools": {"billing_v1": t1, "billing_v2": t2}}


@app.post("/run", dependencies=[Depends(require_user)])
async def run(volume: int = DEFAULT_MONTHLY_VOLUME, explain: bool = True, fresh: bool = False):
    """Streams a run. ``fresh=true`` starts over: clears the billing-v1 cache and the run history."""
    if S.lock.locked():
        raise HTTPException(409, "a run is already in progress")

    async def stream():
        async with S.lock:
            if fresh:
                V1Cache().clear()
                clear_history()
            try:
                async for ev in run_parity(S.v1, S.v2, use_cache=True, explain=explain, monthly_volume=volume,
                                           trace=True):
                    yield _sse(ev)
            except Exception as exc:  # surface failures to the dashboard instead of a dead stream
                yield _sse({"type": "error", "detail": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/runs/{name}", dependencies=[Depends(require_user)])
def get_run(name: str):
    if name not in ("latest", "previous"):
        raise HTTPException(404, "unknown run")
    r = load_run(name)
    if not r:
        raise HTTPException(404, "no run yet")
    return slim_run(r)


@app.get("/runs/latest/scenarios/{sid}", dependencies=[Depends(require_user)])
def get_scenario(sid: str):
    r = load_run("latest")
    for res in (r or {}).get("results", []):
        if res["id"] == sid:
            return res
    raise HTTPException(404, "scenario not found")


@app.get("/report.md", response_class=PlainTextResponse, dependencies=[Depends(require_user)])
def report():
    r = load_run("latest")
    if not r:
        raise HTTPException(404, "no run yet")
    return PlainTextResponse(render_markdown(r), media_type="text/markdown",
                             headers={"Content-Disposition": 'attachment; filename="doppel-parity-report.md"'})


class AdhocIn(BaseModel):
    text: str


@app.post("/adhoc", dependencies=[Depends(require_user)])
async def adhoc(body: AdhocIn):
    try:
        scenario, plan = await plan_scenario(body.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    async with S.lock:
        trace: list[dict[str, Any]] = []
        v1_out, v2_out = await asyncio.gather(run_steps(S.v1, scenario, trace), run_steps(S.v2, scenario, trace))
    diffs = [d.to_dict() for d in compare_outputs(v1_out, v2_out, [s.tool for s in scenario.steps])]
    result = {**scenario.to_dict(), "v1": v1_out, "v2": v2_out, "diffs": diffs, "match": not diffs,
              "impact": impact(v1_out, v2_out), "trace": trace}
    explanation = None
    if diffs:
        group = {"key": "adhoc", "fields": signature(diffs), "scenario_ids": ["JUDGE"]}
        prev = load_run("latest") or {}
        # Reuse a known explanation when this matches an existing mismatch group.
        for g in prev.get("groups", []):
            if g.get("fields") == group["fields"] and g.get("explanation") and g.get("status") != "FIXED":
                explanation = {**g["explanation"], "reused_from": g["key"]}
                break
        if explanation is None:
            diff_text = v2_diff_since(prev.get("v2_commit"), prev.get("v2_snapshot"))
            explanation = (await explain_groups([group], {"JUDGE": result}, diff_text))[0]
    return {"plan": plan, "result": result, "explanation": explanation}
