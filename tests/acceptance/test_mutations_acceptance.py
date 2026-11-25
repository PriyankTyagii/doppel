"""Acceptance: every break-it-live mutation is caught, explained by the right rule, and fully restorable.

Runs against the live stack (billing-v1 on :8001, demo-control on :8090 owning billing-v2 on :8002, and the
Doppel agent on :8000) because the point is to exercise the real restart and git flow. It makes real model
calls to explain the new mismatches. Skips if the stack is not up.

    .venv/bin/python -m pytest tests/acceptance -v -s
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo-control"))
from mutations import MUTATIONS  # noqa: E402

AGENT = "http://localhost:8000"
CONTROL = "http://localhost:8090"


def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not (_up(f"{AGENT}/health") and _up(f"{CONTROL}/state")),
                                reason="needs the live stack: agent :8000 and demo-control :8090")


def run_doppel() -> dict:
    """Streams a run and returns the final run record."""
    with httpx.stream("POST", f"{AGENT}/run", timeout=600) as r:
        r.raise_for_status()
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event in ("done", "error"):
                data = json.loads(line[6:])
                if event == "error":
                    raise AssertionError(data["detail"])
                return data["run"]
    raise AssertionError("run stream ended without a done event")


def explanation_text(group: dict) -> str:
    e = group.get("explanation") or {}
    return " ".join(str(e.get(k, "")) for k in ("cause", "rule", "explanation", "changed_line", "suggested_fix")).lower()


@pytest.fixture(scope="module")
def baseline():
    state = httpx.get(f"{CONTROL}/state").json()
    if state["demo_active"]:
        httpx.post(f"{CONTROL}/restore", timeout=60).raise_for_status()
    run_doppel()  # settle the "previous run" to the clean baseline
    run = run_doppel()
    return run["summary"]


@pytest.mark.parametrize("mutation", MUTATIONS, ids=[m.id for m in MUTATIONS])
def test_mutation_is_caught_explained_and_restored(baseline, mutation):
    applied = httpx.post(f"{CONTROL}/mutations/{mutation.id}/apply", timeout=120)
    assert applied.status_code == 200, applied.text
    info = applied.json()
    assert info["restarted"] and info["healthy_after_s"] < 30
    assert "no synapse rebuild" in info["rebuild"].lower(), "behaviour-only mutations must skip the rebuild"

    try:
        t0 = time.time()
        run = run_doppel()
        elapsed = time.time() - t0
        new_groups = [g for g in run["groups"] if g["status"] == "NEW"]
        print(f"\n[{mutation.id}] parity {run['summary']['parity_pct']}% (baseline {baseline['parity_pct']}%), "
              f"re-run {elapsed:.1f}s, NEW groups:")
        for g in new_groups:
            e = g.get("explanation") or {}
            print(f"    {g['key']} x{len(g['scenario_ids'])}: {e.get('cause')} | {e.get('changed_line')}")

        assert new_groups, f"{mutation.id}: no NEW mismatch reported"
        assert run["counts"]["NEW"] > 0

        def names_rule(g: dict) -> bool:
            text = explanation_text(g)
            return all(any(k in text for k in alts) for alts in mutation.expect_keywords)

        assert any(names_rule(g) for g in new_groups), (
            f"{mutation.id}: no NEW group's explanation names the rule {mutation.expect_keywords}: "
            + "; ".join(explanation_text(g) for g in new_groups))
        assert any((g.get("explanation") or {}).get("recent_change") for g in new_groups), \
            f"{mutation.id}: explanation did not tie the mismatch to the billing-v2 change"
    finally:
        restored = httpx.post(f"{CONTROL}/restore", timeout=120)
        assert restored.status_code == 200, restored.text

    after = run_doppel()
    assert after["summary"]["parity_pct"] == baseline["parity_pct"], "parity must return to the pre-mutation score"
    assert after["summary"]["identical"] == baseline["identical"]
    state = httpx.get(f"{CONTROL}/state").json()
    assert not state["demo_active"] and state["v2_healthy"]
