"""Break-it-live demo control. A human operator (DOPPEL_ADMIN_EMAILS) uses it; the Doppel agent never calls it.

Run: ../.venv/bin/uvicorn app:app --port 8090   (from demo-control/)
It starts and owns billing-v2 on :8002.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import _paths  # noqa: F401
import control
from firebase_auth import allowed_origins, bearer, check_config, require_admin
from mutations import MUTATIONS


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_config()
    if not control.V2_PROC.healthy() or control.V2_PROC.proc is None:
        await run_in_threadpool(control.V2_PROC.restart)
    yield
    control.V2_PROC.stop()


app = FastAPI(title="Doppel demo control", lifespan=lifespan, dependencies=[Depends(require_admin)])
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])


async def _do(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except control.ControlError as exc:
        raise HTTPException(400, str(exc))


class EditIn(BaseModel):
    file: str
    name: str
    source: str


@app.get("/state")
async def state():
    return await run_in_threadpool(control.status)


@app.get("/mutations")
def mutations():
    applied = {a["id"] for a in control.load_state().get("applied", [])}
    return [{**m.to_dict(), "applied": m.id in applied} for m in MUTATIONS]


@app.post("/mutations/{mid}/apply")
async def apply(mid: str, request: Request):
    return await _do(control.apply_mutation, mid, bearer(request))


@app.get("/definitions")
async def definitions():
    return await run_in_threadpool(control.list_definitions)


@app.get("/definitions/{file}/{name}")
async def definition(file: str, name: str):
    return await _do(control.get_definition, file, name)


@app.post("/edit/check")
async def edit_check(body: EditIn):
    """Type-checks a hand edit without applying it."""
    d = await _do(control.get_definition, body.file, body.name)
    path = control.V2 / "src" / body.file
    text = path.read_text().splitlines(keepends=True)
    new_lines = body.source.rstrip("\n").splitlines()
    old_lines = d["source"].splitlines()
    if len(new_lines) != len(old_lines):
        raise HTTPException(400, "edit exactly one line: do not add or remove lines")
    for i, line in enumerate(new_lines):
        eol = "\n" if text[d["start"] - 1 + i].endswith("\n") else ""
        text[d["start"] - 1 + i] = line + eol
    ok, msg = await run_in_threadpool(control.typecheck, body.file, "".join(text))
    return {"ok": ok, "typecheck": msg or "ok"}


@app.post("/edit/apply")
async def edit_apply(body: EditIn, request: Request):
    return await _do(control.apply_edit, body.file, body.name, body.source, bearer(request))


@app.post("/restore")
async def restore():
    out = await _do(control.restore)
    out["healthy_after_s"] = await _do(control.V2_PROC.restart)
    return out


@app.post("/v2/restart")
async def restart():
    return {"healthy_after_s": await _do(control.V2_PROC.restart)}
