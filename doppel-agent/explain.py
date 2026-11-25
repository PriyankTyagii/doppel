"""Explain a group of mismatches from the code of both systems.

Read-only by design: reads source files and the git diff of billing-v2, never writes to either repo.
It may *suggest* a fix for a human to apply.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import _paths  # noqa: F401  (puts common/ on sys.path)
import code_slice
import llm

ROOT = Path(__file__).resolve().parent.parent
V2_GLOB = "billing-v2/src/*.ts"


class Explanation(BaseModel):
    cause: str = Field(description="Short title of the root cause, e.g. 'Sunday late-fee waiver missing in v2'.")
    rule: str = Field(description="The business rule involved, in a few words, e.g. 'late fee', 'GST rounding'.")
    v1_file: str = Field(description="Repo-relative path in billing-v1 that implements the reference behaviour.")
    v1_line: int
    v2_file: str = Field(description="Repo-relative path in billing-v2 that behaves differently.")
    v2_line: int
    explanation: str = Field(description="One sentence: what v1 does, what v2 does, and the effect on the bill.")
    suggested_fix: str = Field(description="A minimal change to billing-v2 for a human to apply.")
    recent_change: bool = Field(description="True if a line in the billing-v2 diff since the last run caused this.")
    changed_line: str = Field(description="If recent_change: 'path:line  <the changed line>'. Otherwise empty.")


class GroupExplanation(Explanation):
    group: int = Field(description="The group number this explains.")


class Explanations(BaseModel):
    groups: list[GroupExplanation]


def v2_snapshot() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): p.read_text() for p in sorted(ROOT.glob(V2_GLOB))}


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def v2_commit() -> str:
    return git("rev-parse", "HEAD").strip()


def v2_diff_since(prev_commit: str | None, prev_snapshot: dict[str, str] | None) -> str:
    """The billing-v2 diff since the previous run: git diff from that run's commit (committed and
    uncommitted changes), falling back to a diff against that run's source snapshot."""
    if prev_commit:
        out = git("diff", "--unified=2", prev_commit, "--", "billing-v2/src")
        log = git("log", "--format=%h %s", f"{prev_commit}..HEAD", "--", "billing-v2")
        if out.strip():
            return (f"Commits since last run:\n{log}\n" if log.strip() else "") + out
    if prev_snapshot:
        import difflib

        now = v2_snapshot()
        chunks = []
        for path in sorted(set(now) | set(prev_snapshot)):
            a, b = prev_snapshot.get(path, "").splitlines(), now.get(path, "").splitlines()
            if a != b:
                chunks.append("\n".join(difflib.unified_diff(a, b, f"a/{path}", f"b/{path}", n=2, lineterm="")))
        return "\n".join(chunks)
    return ""


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_lines(diff_text: str) -> list[tuple[str, int, str]]:
    """(path, line number in the current file, text) for every line the diff adds."""
    out: list[tuple[str, int, str]] = []
    path, line = "", 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif m := _HUNK.match(raw):
            line = int(m.group(1))
        elif raw.startswith("+") and path:
            out.append((path, line, raw[1:]))
            line += 1
        elif (raw.startswith(" ") or raw == "") and path:
            line += 1
    return out


def pin_changed_line(exp: dict[str, Any], diff_text: str) -> dict[str, Any]:
    """Replaces the model's line number with the exact one from the diff when the quoted code matches."""
    quoted = exp.get("changed_line") or ""
    best = None
    for path, line, text in added_lines(diff_text):
        if text.strip() and text.strip() in quoted:
            if best is None or len(text.strip()) > len(best[2].strip()):
                best = (path, line, text)
    if best:
        exp["changed_line"] = f"{best[0]}:{best[1]}  {best[2].strip()}"
        exp["changed_file"], exp["changed_line_no"] = best[0], best[1]
        exp["recent_change"] = True
    return exp


SYSTEM = """You are Doppel, a parity checker. billing-v1 (Python, legacy) is the reference: its behaviour is \
correct by definition, including rules nobody documented. billing-v2 (TypeScript) is an AI rewrite that must \
behave identically.

You are given numbered groups of scenarios where the two systems returned different outputs, and the code both \
systems ran for them. For each group, find the root cause in the code and return one entry with that group's \
number. Cite the exact file and line number (shown at the left of each source line) in each system. Be concrete \
and short. Never claim a cause you cannot point to in the code.

If the "billing-v2 changes since the last run" diff contains the line that causes a group's mismatch, set \
recent_change to true and quote that line in changed_line as "path:line  <code>" using the line number in the \
current file."""


def _group_block(number: int, group: dict[str, Any], examples: list[dict[str, Any]]) -> str:
    context = {
        "new": "These scenarios were IDENTICAL on both systems in the previous run, so a change in billing-v2 "
               "since then caused this: check the diff first.",
        "changed": "These scenarios already differed in the previous run, but billing-v2 now returns DIFFERENT "
                   "values: explain what changed since the last run (diff and previous v2 values); mention the "
                   "older known cause only briefly.",
    }.get(group.get("origin", ""), "")
    lines = [f"## Group {number}: fields {', '.join(group['fields'])}; {len(group['scenario_ids'])} scenarios"]
    if context:
        lines.append(context)
    for ex in examples:
        lines.append(f"Scenario {ex['id']}: {ex['summary']}")
        lines.append("  Steps: " + json.dumps([{"tool": s["tool"], "args": s["args"]} for s in ex["steps"]]))
        before = {d["path"]: d["v2"] for d in ex.get("prev_diffs") or []}
        for d in ex["diffs"][:8]:
            delta = f" (v2 - v1 = Rs {d['delta']})" if d.get("delta") is not None else ""
            was = f" [previous run: v2={json.dumps(before[d['path']])}]" if d["path"] in before else ""
            lines.append(f"  {d['path']}: v1={json.dumps(d['v1'])} v2={json.dumps(d['v2'])}{delta}{was}")
    return "\n".join(lines)


def fallback_explanation(group: dict[str, Any], diff_text: str, reason: str) -> dict[str, Any]:
    """Used when the model is unavailable: no root cause claimed, only what changed."""
    changed = next((l[1:].strip() for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++")), "")
    return {
        "cause": f"Unexplained difference in {', '.join(group['fields'])}",
        "rule": "unknown",
        "v1_file": "", "v1_line": 0, "v2_file": "", "v2_line": 0,
        "explanation": f"Explainer unavailable ({reason}).",
        "suggested_fix": "",
        "recent_change": bool(changed),
        "changed_line": changed,
        "source": "fallback",
    }


async def explain_groups(groups: list[dict[str, Any]], results_by_id: dict[str, dict[str, Any]],
                         diff_text: str) -> list[dict[str, Any]]:
    """Explains all groups in one request (the free tier is rate-limited per minute). Returns explanations
    in the same order as ``groups``; a group the model leaves out gets the fallback."""
    if not groups:
        return []
    if not llm.configured():
        return [fallback_explanation(g, diff_text, "GROQ_API_KEY is not set") for g in groups]
    examples = [[results_by_id[sid] for sid in g["scenario_ids"][:2] if sid in results_by_id] for g in groups]
    tools = {s["tool"] for exs in examples for ex in exs for s in ex.get("steps", [])}
    prompt = "\n\n".join(
        [code_slice.relevant_source(tools)]
        + [_group_block(i + 1, g, exs) for i, (g, exs) in enumerate(zip(groups, examples))]
        + ([f"billing-v2 changes since the last run:\n```diff\n{diff_text[:6000]}\n```"] if diff_text
           else ["billing-v2 has not changed since the last run."])
        + [f"Return exactly {len(groups)} entries, one for each group number 1 to {len(groups)}. Groups may share "
           "a cause; explain each one anyway."]
    )
    try:
        reply = await llm.complete_json(SYSTEM, prompt, Explanations, max_tokens=1500)
    except llm.LLMError as exc:
        return [fallback_explanation(g, diff_text, str(exc)) for g in groups]
    by_number = {e.group: e for e in reply.groups}
    out = []
    for i, g in enumerate(groups):
        e = by_number.get(i + 1)
        if e is None:
            out.append(fallback_explanation(g, diff_text, "the model returned no explanation for this group"))
            continue
        item = e.model_dump(exclude={"group"})
        item["source"] = "model"
        out.append(pin_changed_line(item, diff_text))
    return out
