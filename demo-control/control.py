"""Demo-control operations: git on the live-demo branch, the billing-v2 process, edits and type checks.

Only ever touches billing-v2. billing-v1 is the reference and is never modified.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from mutations import BY_ID, Mutation

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "billing-v2"
V2_REL = "billing-v2"
STATE_FILE = Path(__file__).resolve().parent / "state.json"
BRANCH = "live-demo"
V2_PORT = int(os.environ.get("BILLING_V2_PORT", "8002"))
V2_URL = f"http://localhost:{V2_PORT}"
AGENT_URL = os.environ.get("DOPPEL_AGENT_URL", "http://localhost:8000")
ROUTE_LINE = re.compile(r"\bapp\.(get|post|put|patch|delete)\s*\(")


class ControlError(Exception):
    pass


# --------------------------------------------------------------------------- git

def git(*args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise ControlError(f"git {' '.join(args)} failed: {p.stderr.strip() or p.stdout.strip()}")
    return p.stdout.strip()


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except ValueError:
            pass
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=1))


def v2_dirty() -> bool:
    return bool(git("status", "--porcelain", "--", V2_REL))


def arm() -> dict[str, Any]:
    """Switches the repo to the live-demo branch, remembering where the demo started."""
    state = load_state()
    if current_branch() == BRANCH and state.get("pre_demo_commit"):
        return state
    if v2_dirty():
        raise ControlError("billing-v2 has uncommitted changes; commit or stash them before the demo")
    state = {
        "original_branch": current_branch(),
        "pre_demo_commit": git("rev-parse", "HEAD"),
        "applied": [],
    }
    git("switch", "-C", BRANCH)
    save_state(state)
    return state


def commit_v2(rel_file: str, message: str) -> str:
    path = f"{V2_REL}/{rel_file}"
    git("add", "--", path)
    git("commit", "-q", "-m", message, "--", path)
    return git("rev-parse", "--short", "HEAD")


def restore() -> dict[str, Any]:
    """Puts billing-v2 back exactly as it was before the demo and returns to the original branch."""
    state = load_state()
    pre = state.get("pre_demo_commit")
    if not pre:
        raise ControlError("no demo in progress (nothing to restore)")
    # Drop any half-applied hand edit in billing-v2 only.
    git("checkout", "--", V2_REL, check=False)
    if current_branch() == BRANCH:
        git("switch", state.get("original_branch") or "main")
    # If the original branch moved during the demo, still force billing-v2 back to the pre-demo tree.
    if git("diff", "--name-only", pre, "--", V2_REL):
        git("restore", f"--source={pre}", "--staged", "--worktree", "--", V2_REL)
    save_state({})
    return {"restored_to": pre[:8], "branch": current_branch()}


# ---------------------------------------------------------------- billing-v2 process

@dataclass
class V2Process:
    proc: subprocess.Popen | None = None

    def _port_pids(self) -> list[int]:
        out = subprocess.run(["lsof", "-ti", f"tcp:{V2_PORT}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        return [int(x) for x in out.split()]

    def _is_billing_v2(self, pid: int) -> bool:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
        cwd = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
        return "server.ts" in cmd or "billing-v2" in cmd or str(V2) in cwd

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
        self.proc = None
        # A billing-v2 started outside demo-control (e.g. `npm run dev`) would keep the port.
        for pid in self._port_pids():
            if self._is_billing_v2(pid):
                os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 5
        while self._port_pids() and time.time() < deadline:
            time.sleep(0.1)
        if self._port_pids():
            raise ControlError(f"port {V2_PORT} is held by a process that is not billing-v2; stop it first")

    def start(self) -> None:
        log = open(Path(__file__).resolve().parent / "billing-v2.log", "a")
        tsx = V2 / "node_modules" / ".bin" / "tsx"
        self.proc = subprocess.Popen(
            [str(tsx), "src/server.ts"], cwd=V2, env={**os.environ, "PORT": str(V2_PORT)},
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

    def healthy(self) -> bool:
        try:
            return httpx.get(f"{V2_URL}/health", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    def wait_healthy(self, timeout: float = 30) -> float:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc and self.proc.poll() is not None:
                raise ControlError("billing-v2 exited on start; see demo-control/billing-v2.log")
            if self.healthy():
                return round(time.time() - t0, 2)
            time.sleep(0.2)
        raise ControlError(f"billing-v2 did not answer /health within {timeout}s")

    def restart(self) -> float:
        self.stop()
        self.start()
        return self.wait_healthy()


V2_PROC = V2Process()


# --------------------------------------------------------- synapse + agent reconnect

def synapse_discover() -> dict[str, Any]:
    exe = shutil.which("synapse")
    if not exe:
        return {"ran": False, "detail": "synapse CLI not installed; run `synapse build --discover` in billing-v2 by hand"}
    p = subprocess.run([exe, "build", "--discover"], cwd=V2, capture_output=True, text=True, timeout=600)
    return {"ran": True, "ok": p.returncode == 0, "detail": (p.stdout + p.stderr)[-2000:]}


def agent_reconnect(token: str = "") -> dict[str, Any]:
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = httpx.post(f"{AGENT_URL}/reconnect", headers=headers, timeout=60)
        return r.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"could not reach the Doppel agent: {exc}"}


def after_change(changes_endpoints: bool, token: str = "") -> dict[str, Any]:
    """Restart billing-v2; rebuild the MCP server only when the API surface changed."""
    secs = V2_PROC.restart()
    out: dict[str, Any] = {"restarted": True, "healthy_after_s": secs}
    if changes_endpoints:
        out["synapse"] = synapse_discover()
        out["agent"] = agent_reconnect(token)
        out["rebuild"] = "Endpoint changed: ran `synapse build --discover` and told Doppel to re-list tools."
    else:
        out["rebuild"] = ("Behaviour-only change: no Synapse rebuild needed, the MCP server calls the running "
                          "billing-v2 API.")
    return out


# ------------------------------------------------------------------------ mutations

def apply_mutation(mid: str, token: str = "") -> dict[str, Any]:
    m: Mutation | None = BY_ID.get(mid)
    if not m:
        raise ControlError(f"unknown mutation {mid}")
    state = arm()
    path = V2 / m.file
    text = path.read_text()
    if m.replace in text:
        raise ControlError(f"'{m.title}' is already applied")
    if text.count(m.find) != 1:
        raise ControlError(f"cannot apply '{m.title}': the target line was not found exactly once in {m.file}")
    line_no = text[: text.index(m.find)].count("\n") + 1
    path.write_text(text.replace(m.find, m.replace))
    sha = commit_v2(m.file, f"live-demo: {m.title}")
    state.setdefault("applied", []).append({"id": m.id, "title": m.title, "commit": sha,
                                            "file": f"{V2_REL}/{m.file}", "line": line_no})
    save_state(state)
    return {"mutation": m.to_dict(), "commit": sha, "file": f"{V2_REL}/{m.file}", "line": line_no,
            **after_change(m.changes_endpoints, token)}


# ----------------------------------------------------------- hand edit of one line

# Infrastructure files (schema, db handle) are not offered for hand edits.
HAND_EDIT_EXCLUDED = {"db.ts"}
_DEF = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*(?::[^=]+)?=)")


def list_definitions() -> list[dict[str, Any]]:
    out = []
    for p in sorted((V2 / "src").glob("*.ts")):
        if p.name in HAND_EDIT_EXCLUDED:
            continue
        lines = p.read_text().splitlines()
        i = 0
        while i < len(lines):
            m = _DEF.match(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1) or m.group(2)
            end = _block_end(lines, i)
            out.append({"file": p.name, "name": name, "start": i + 1, "end": end + 1})
            i = end + 1
    return out


def _block_end(lines: list[str], start: int) -> int:
    depth = 0
    opened = False
    for j in range(start, len(lines)):
        for ch in lines[j]:
            if ch in "{([":
                depth += 1
                opened = True
            elif ch in "})]":
                depth -= 1
        if (opened and depth <= 0) or (not opened and lines[j].rstrip().endswith(";")):
            if lines[j].rstrip().endswith((";", "}", "};")) or depth <= 0:
                return j
    return len(lines) - 1


def get_definition(file: str, name: str) -> dict[str, Any]:
    d = next((d for d in list_definitions() if d["file"] == file and d["name"] == name), None)
    if not d:
        raise ControlError(f"{name} not found in {file}")
    lines = (V2 / "src" / file).read_text().splitlines()
    return {**d, "source": "\n".join(lines[d["start"] - 1: d["end"]])}


def typecheck(file: str, new_text: str) -> tuple[bool, str]:
    """Type-checks billing-v2 with one file replaced, in a scratch copy (the real tree is untouched)."""
    scratch = V2 / ".typecheck"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(V2 / "src", scratch / "src")
    (scratch / "src" / file).write_text(new_text)
    (scratch / "tsconfig.json").write_text(json.dumps({"extends": "../tsconfig.json", "include": ["src"]}))
    p = subprocess.run([str(V2 / "node_modules" / ".bin" / "tsc"), "-p", str(scratch / "tsconfig.json")],
                       capture_output=True, text=True, timeout=120)
    shutil.rmtree(scratch, ignore_errors=True)
    msg = (p.stdout + p.stderr).replace(str(scratch) + "/", "billing-v2/")
    return p.returncode == 0, msg.strip()


def apply_edit(file: str, name: str, new_source: str, token: str = "") -> dict[str, Any]:
    d = get_definition(file, name)
    old_lines = d["source"].splitlines()
    new_lines = new_source.rstrip("\n").splitlines()
    if len(old_lines) != len(new_lines):
        raise ControlError("edit exactly one line: do not add or remove lines")
    changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
    if len(changed) != 1:
        raise ControlError(f"edit exactly one line (you changed {len(changed)})")
    idx = changed[0]
    path = V2 / "src" / file
    all_lines = path.read_text().splitlines(keepends=True)
    line_no = d["start"] + idx
    eol = "\n" if all_lines[line_no - 1].endswith("\n") else ""
    all_lines[line_no - 1] = new_lines[idx] + eol
    new_text = "".join(all_lines)
    ok, msg = typecheck(file, new_text)
    if not ok:
        return {"applied": False, "typecheck": msg}
    state = arm()
    path.write_text(new_text)
    sha = commit_v2(f"src/{file}", f"live-demo: hand edit in {name}()")
    endpoint = bool(ROUTE_LINE.search(old_lines[idx]) or ROUTE_LINE.search(new_lines[idx]))
    state.setdefault("applied", []).append({"id": "hand_edit", "title": f"Hand edit in {name}()", "commit": sha,
                                            "file": f"{V2_REL}/src/{file}", "line": line_no,
                                            "before": old_lines[idx].strip(), "after": new_lines[idx].strip()})
    save_state(state)
    return {"applied": True, "typecheck": "ok", "commit": sha, "file": f"{V2_REL}/src/{file}", "line": line_no,
            "before": old_lines[idx], "after": new_lines[idx], **after_change(endpoint, token)}


def status() -> dict[str, Any]:
    state = load_state()
    return {
        "branch": current_branch(),
        "demo_active": bool(state.get("pre_demo_commit")),
        "pre_demo_commit": (state.get("pre_demo_commit") or "")[:8],
        "applied": state.get("applied", []),
        "v2_healthy": V2_PROC.healthy(),
        "v2_managed": bool(V2_PROC.proc and V2_PROC.proc.poll() is None),
    }
