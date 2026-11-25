"""Command line: `python cli.py run [--mode http|mcp] [--no-explain] [--no-cache]`, `python cli.py scenarios`."""

from __future__ import annotations

import argparse
import asyncio
import json

from backends import make_backends
from pipeline import run_parity
from report import render_markdown
from scenarios import generate


async def _run(args: argparse.Namespace) -> None:
    v1, v2 = make_backends(args.mode, args.mcp_config)
    await v1.connect()
    await v2.connect()
    try:
        async for ev in run_parity(v1, v2, use_cache=not args.no_cache, explain=not args.no_explain,
                                   monthly_volume=args.volume):
            if ev["type"] == "result":
                r = ev["result"]
                mark = "  ok " if r["match"] else f"{r['status']:>5}"
                print(f"{mark} {r['id']} {r['summary']}")
            elif ev["type"] == "explaining":
                print(f"... explaining {ev['groups']} group(s) from the code")
            elif ev["type"] == "done":
                run = ev["run"]
                print()
                print(render_markdown(run) if args.report else run["summary"]["headline"])
                s = run["summary"]
                print(f"\nParity: {s['identical']}/{s['total']} identical ({s['parity_pct']}%) in {run['duration_s']}s  "
                      f"counts={json.dumps(run['counts'])}")
    finally:
        await v1.close()
        await v2.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="doppel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run a parity check")
    run.add_argument("--mode", choices=["http", "mcp"], default="mcp")
    run.add_argument("--mcp-config", default=None)
    run.add_argument("--no-explain", action="store_true")
    run.add_argument("--no-cache", action="store_true", help="call billing-v1 too instead of using cached results")
    run.add_argument("--volume", type=int, default=100_000, help="monthly invoice volume for the projection")
    run.add_argument("--report", action="store_true", help="print the full Markdown report")
    sub.add_parser("scenarios", help="list the scenarios")
    args = ap.parse_args()
    if args.cmd == "scenarios":
        for s in generate():
            print(s.id, s.kind.ljust(22), s.summary)
    else:
        asyncio.run(_run(args))


if __name__ == "__main__":
    main()
