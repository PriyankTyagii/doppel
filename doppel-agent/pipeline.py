"""One parity run: execute scenarios, diff, classify against the previous run, group, explain, score."""

from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from backends import Backend
from compare import compare_outputs, impact
from explain import explain_groups, v2_commit, v2_diff_since, v2_snapshot
from runner import V1Cache, run_all
from scenarios import Scenario, generate

RUNS_DIR = Path(__file__).resolve().parent / "runs"
DEFAULT_MONTHLY_VOLUME = 100_000
DERIVED_FIELDS = {"total", "amount_paid", "refunded"}
GST_SPLIT = {"cgst", "sgst", "igst"}


def signature(diffs: list[dict[str, Any]]) -> list[str]:
    """Fields that identify a mismatch's cause. Derived totals are dropped when a root field also differs."""
    fields = {("gst_split" if d["field"] in GST_SPLIT else d["field"]) for d in diffs}
    core = fields - DERIVED_FIELDS
    return sorted(core or fields)


def clear_history() -> None:
    for name in ("latest", "previous"):
        (RUNS_DIR / f"{name}.json").unlink(missing_ok=True)


def load_run(name: str = "latest") -> dict[str, Any] | None:
    p = RUNS_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def _save_run(run: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    latest = RUNS_DIR / "latest.json"
    if latest.exists():
        latest.replace(RUNS_DIR / "previous.json")
    latest.write_text(json.dumps(run, indent=1))


def classify(result: dict[str, Any], prev: dict[str, Any] | None) -> str:
    """NEW / FIXED / UNCHANGED (mismatch seen before, same values) / OK (identical both times)."""
    now_bad = not result["match"]
    if prev is None:
        return "NEW" if now_bad else "OK"
    prev_bad = not prev["match"]
    if now_bad and not prev_bad:
        return "NEW"
    if not now_bad and prev_bad:
        return "FIXED"
    if not now_bad:
        return "OK"
    before = {d["path"]: d["v2"] for d in prev["diffs"]}
    changed = any(d["path"] not in before or before[d["path"]] != d["v2"] for d in result["diffs"])
    return "NEW" if changed else "UNCHANGED"


def group_impact(results: list[dict[str, Any]], total_scenarios: int, monthly_volume: int) -> dict[str, Any]:
    bill = [r["impact"]["bill_delta"] for r in results]
    tax = [r["impact"]["tax_delta"] for r in results]
    rupees_wrong = round(sum(abs(x) for x in bill), 2)
    tax_wrong = round(sum(abs(x) for x in tax), 2)
    return {
        "invoices_affected": len(results),
        "rupees_wrong": rupees_wrong,
        "tax_misreported": tax_wrong,
        "overcharged": sum(1 for x in bill if x > 0),
        "undercharged": sum(1 for x in bill if x < 0),
        "tax_only": sum(1 for b, t in zip(bill, tax) if b == 0 and t != 0),
        "overcharged_rupees": round(sum(x for x in bill if x > 0), 2),
        "undercharged_rupees": round(-sum(x for x in bill if x < 0), 2),
        "projected_monthly_invoices": round(monthly_volume * len(results) / total_scenarios),
        "projected_monthly_rupees": round(monthly_volume * rupees_wrong / total_scenarios, 2),
        "projected_monthly_tax": round(monthly_volume * tax_wrong / total_scenarios, 2),
    }


def summarise(results: list[dict[str, Any]], monthly_volume: int) -> dict[str, Any]:
    total = len(results)
    bad = [r for r in results if not r["match"]]
    imp = group_impact(bad, total, monthly_volume) if total else {}
    pct_identical = round(100 * (total - len(bad)) / total, 1) if total else 0.0
    pct_wrong = round(100 - pct_identical, 1)
    headline = (
        f"If you switched today: {pct_wrong:g}% of bills wrong, "
        f"~₹{_inr(imp.get('projected_monthly_rupees', 0))}/month mis-billed and "
        f"~₹{_inr(imp.get('projected_monthly_tax', 0))}/month GST misreported (projected)."
        if bad else "If you switched today: every bill in the sample matches the legacy system."
    )
    return {
        "identical": total - len(bad),
        "total": total,
        "parity_pct": pct_identical,
        "impact": imp,
        "monthly_volume": monthly_volume,
        "headline": headline,
        "projection_note": f"Projection: sample of {total} scenarios scaled to {_inr(monthly_volume)} invoices/month.",
    }


def _inr(x: float) -> str:
    """Indian digit grouping: 1234567.8 -> '12,34,568'."""
    n = int(round(x))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if n < 0 else "") + s


async def run_parity(
    v1: Backend,
    v2: Backend,
    scenarios: list[Scenario] | None = None,
    *,
    use_cache: bool = True,
    explain: bool = True,
    monthly_volume: int = DEFAULT_MONTHLY_VOLUME,
    save: bool = True,
    trace: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Yields events: start, result (per scenario), explaining, group (per mismatch group), done."""
    scenarios = scenarios or generate()
    prev_run = load_run("latest")
    prev_by_id = {r["id"]: r for r in (prev_run or {}).get("results", [])}
    prev_groups = {g["key"]: g for g in (prev_run or {}).get("groups", [])}
    cache = V1Cache() if use_cache else None
    started = time.time()
    run_id = uuid.uuid4().hex[:8]
    yield {"type": "start", "run_id": run_id, "total": len(scenarios), "v1_cached": bool(cache and cache.data)}

    results: list[dict[str, Any]] = []
    identical = 0
    async for r in run_all(v1, v2, scenarios, cache, trace=trace):
        sc: Scenario = r["scenario"]
        diffs = [d.to_dict() for d in compare_outputs(r["v1"], r["v2"], [s.tool for s in sc.steps])]
        result = {
            **sc.to_dict(),
            "v1": r["v1"], "v2": r["v2"], "v1_cached": r["v1_cached"],
            "diffs": diffs, "match": not diffs,
            "impact": impact(r["v1"], r["v2"]),
            "trace": r["trace"],
        }
        result["status"] = classify(result, prev_by_id.get(sc.id))
        result["signature"] = signature(diffs) if diffs else []
        identical += result["match"]
        results.append(result)
        yield {"type": "result", "result": _slim(result), "done": len(results), "identical": identical}

    # Group mismatches. A fresh break gets its own card: scenarios that matched last time ("new"), scenarios
    # that already differed but whose v2 output changed ("changed"), and known mismatches are grouped apart.
    groups: dict[str, dict[str, Any]] = {}
    for r in results:
        if r["match"]:
            continue
        prev = prev_by_id.get(r["id"])
        if r["status"] != "NEW":
            origin = "known"
        elif prev is None:
            origin = "first" if prev_run is None else "new"
        else:
            origin = "changed" if not prev["match"] else "new"
        if origin == "changed":
            r["prev_diffs"] = prev["diffs"]
        key = f"{'new' if origin == 'first' else origin}:" + "|".join(r["signature"])
        g = groups.setdefault(key, {"key": key, "fields": r["signature"], "scenario_ids": [], "origin": origin,
                                    "status": "UNCHANGED" if origin == "known" else "NEW",
                                    "first_run": origin == "first"})
        g["scenario_ids"].append(r["id"])
        r["group"] = key

    by_id = {r["id"]: r for r in results}
    diff_text = v2_diff_since((prev_run or {}).get("v2_commit"), (prev_run or {}).get("v2_snapshot"))
    to_explain = []
    for g in groups.values():
        sig = g["key"].split(":", 1)[1]
        reuse = next((prev_groups[k] for k in (f"known:{sig}", f"new:{sig}", f"changed:{sig}") if k in prev_groups), None)
        if g["status"] == "UNCHANGED" and reuse and reuse.get("explanation"):
            g["explanation"] = reuse["explanation"]
        else:
            to_explain.append(g)

    if explain and to_explain:
        yield {"type": "explaining", "groups": len(to_explain)}
        for g, exp in zip(to_explain, await explain_groups(to_explain, by_id, diff_text)):
            g["explanation"] = exp

    groups = _merge_same_change(groups)

    # Groups that disappeared since the last run are FIXED.
    fixed_ids = {r["id"] for r in results if r["status"] == "FIXED"}
    fixed_groups = []
    for key, pg in prev_groups.items():
        if pg.get("status") == "FIXED":
            continue
        ids = [sid for sid in pg["scenario_ids"] if sid in fixed_ids]
        if ids:
            fixed_groups.append({**pg, "key": "fixed:" + key.split(":", 1)[-1], "status": "FIXED", "scenario_ids": ids})

    total = len(results)
    ordered = sorted(groups.values(), key=lambda g: (g["status"] != "NEW", -len(g["scenario_ids"])))
    for g in ordered + fixed_groups:
        members = [by_id[sid] for sid in g["scenario_ids"]] if g["status"] != "FIXED" else [
            prev_by_id[sid] for sid in g["scenario_ids"] if sid in prev_by_id]
        g["impact"] = group_impact(members, total, monthly_volume)
        yield {"type": "group", "group": g}

    summary = summarise(results, monthly_volume)
    prev_summary = (prev_run or {}).get("summary")
    run = {
        "run_id": run_id,
        "started_at": dt.datetime.fromtimestamp(started, dt.timezone.utc).isoformat(timespec="seconds"),
        "duration_s": round(time.time() - started, 2),
        "v1_backend": type(v1).__name__,
        "v2_backend": type(v2).__name__,
        "v2_commit": v2_commit(),
        "v2_snapshot": v2_snapshot(),
        "v2_diff": diff_text,
        "summary": summary,
        "previous_summary": prev_summary,
        "counts": {s: sum(1 for r in results if r["status"] == s) for s in ("NEW", "FIXED", "UNCHANGED", "OK")},
        "groups": ordered + fixed_groups,
        "results": results,
    }
    if save:
        _save_run(run)
    yield {"type": "done", "run": slim_run(run)}


def _merge_same_change(groups: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One card per fresh break: NEW groups traced to the same changed line are merged."""
    merged: dict[str, dict[str, Any]] = {}
    by_change: dict[str, str] = {}
    # Prefer the group of scenarios that were identical last time: its explanation is about the change alone.
    order = sorted(groups.values(), key=lambda g: (g.get("origin") != "new", -len(g["scenario_ids"])))
    for g in order:
        e = g.get("explanation") or {}
        loc = f"{e.get('changed_file')}:{e.get('changed_line_no')}" if e.get("changed_file") else ""
        if g["status"] == "NEW" and e.get("recent_change") and loc:
            if loc in by_change:
                target = merged[by_change[loc]]
                target["scenario_ids"] += g["scenario_ids"]
                target["fields"] = sorted(set(target["fields"]) | set(g["fields"]))
                target.setdefault("merged_from", [target["key"]]).append(g["key"])
                continue
            by_change[loc] = g["key"]
        merged[g["key"]] = g
    return merged


def _slim(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r[k] for k in ("id", "kind", "summary", "tags", "match", "status", "diffs", "impact", "v1_cached")}


def slim_run(run: dict[str, Any]) -> dict[str, Any]:
    """The run without source snapshots, for the dashboard."""
    return {k: v for k, v in run.items() if k not in ("v2_snapshot",)}
