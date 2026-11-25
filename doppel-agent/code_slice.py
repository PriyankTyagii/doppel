"""Select the code a set of scenarios actually exercises, to keep LLM requests small.

Starting from the HTTP handlers the scenarios called, follow references to other top-level functions and
constants (transitively) in each codebase. Output keeps original line numbers so citations stay exact.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from backends import LOGICAL_TOOLS

ROOT = Path(__file__).resolve().parent.parent
V1_FILE = ROOT / "billing-v1" / "main.py"
V2_DIR = ROOT / "billing-v2" / "src"
_IDENT = re.compile(r"[A-Za-z_]\w*")


@dataclass
class Definition:
    file: Path
    name: str
    start: int  # 1-based, inclusive
    end: int
    route: tuple[str, str] | None  # (METHOD, path pattern) for HTTP handlers
    text: str

    def refs(self) -> set[str]:
        return set(_IDENT.findall(self.text))


def _route_key(method: str, path: str) -> tuple[str, str]:
    """Normalise /invoices/{iid}/pay and /invoices/:id/pay to the same key."""
    return method.upper(), re.sub(r"\{\w+\}|:\w+", "{}", path)


def python_definitions(path: Path) -> list[Definition]:
    src = path.read_text()
    lines = src.splitlines()
    out = []
    for node in ast.parse(src).body:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        end = node.end_lineno or node.lineno
        text = "\n".join(lines[start - 1:end])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            route = None
            for d in getattr(node, "decorator_list", []):
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.args
                        and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)):
                    route = _route_key(d.func.attr, d.args[0].value)
            out.append(Definition(path, node.name, start, end, route, text))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.append(Definition(path, t.id, start, end, None, text))
    return out


# Behaviour only: functions and constants. Types, interfaces and request models are left out.
_TS_DEF = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|(?:const|let)\s+(\w+)\b|class\s+(\w+))")
_TS_ROUTE = re.compile(r'^app\.(get|post|put|patch|delete)\(\s*"([^"]+)"')


def _ts_block_end(lines: list[str], start: int) -> int:
    depth, opened = 0, False
    for j in range(start, len(lines)):
        stripped = re.sub(r'"[^"]*"|\'[^\']*\'|`[^`]*`', '""', lines[j])
        for ch in stripped:
            if ch in "{([":
                depth += 1
                opened = True
            elif ch in "})]":
                depth -= 1
        if depth <= 0 and (opened or stripped.rstrip().endswith((";", "}"))):
            return j
    return len(lines) - 1


def typescript_definitions(directory: Path) -> list[Definition]:
    out = []
    for path in sorted(directory.glob("*.ts")):
        lines = path.read_text().splitlines()
        i = 0
        while i < len(lines):
            m, r = _TS_DEF.match(lines[i]), _TS_ROUTE.match(lines[i])
            if not (m or r):
                i += 1
                continue
            end = _ts_block_end(lines, i)
            text = "\n".join(lines[i:end + 1])
            if r:
                out.append(Definition(path, f"route {r.group(2)}", i + 1, end + 1, _route_key(r.group(1), r.group(2)), text))
            else:
                out.append(Definition(path, next(g for g in m.groups() if g), i + 1, end + 1, None, text))
            i = end + 1
    return out


def _closure(defs: list[Definition], tools: set[str]) -> list[Definition]:
    by_name: dict[str, list[Definition]] = {}
    for d in defs:
        by_name.setdefault(d.name, []).append(d)
    wanted = {_route_key(*LOGICAL_TOOLS[t]) for t in tools if t in LOGICAL_TOOLS and t != "reset"}
    queue = [d for d in defs if d.route in wanted]
    seen: dict[int, Definition] = {}
    while queue:
        d = queue.pop()
        if id(d) in seen:
            continue
        seen[id(d)] = d
        for ref in d.refs():
            if ref != d.name:
                queue.extend(by_name.get(ref, []))
    return sorted(seen.values(), key=lambda d: (d.file.name, d.start))


def render(defs: list[Definition]) -> str:
    """Numbered source, grouped by file, with '...' where lines were left out."""
    parts = []
    for file in sorted({d.file for d in defs}, key=lambda p: p.as_posix()):
        lines = file.read_text().splitlines()
        rel = file.relative_to(ROOT).as_posix()
        spans = sorted((d.start, d.end) for d in defs if d.file == file)
        merged: list[list[int]] = []
        for s, e in spans:
            if merged and s <= merged[-1][1] + 2:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        body = []
        for s, e in merged:
            body.append("\n".join(f"{n:4d}  {lines[n - 1]}" for n in range(s, e + 1) if lines[n - 1].strip()))
        parts.append(f"=== {rel} ===\n" + "\n ...\n".join(body))
    return "\n\n".join(parts)


def relevant_source(tools: set[str]) -> str:
    """The code both systems run for these tools: v1 (reference) first, then v2."""
    v1 = _closure(python_definitions(V1_FILE), tools)
    v2 = _closure(typescript_definitions(V2_DIR), tools)
    return ("--- billing-v1 (legacy, the reference) ---\n" + render(v1) +
            "\n\n--- billing-v2 (rewrite) ---\n" + render(v2))
