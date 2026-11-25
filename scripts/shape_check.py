"""Confirms billing-v1 and billing-v2 return the same JSON shape (keys and value types) for every endpoint.

Values may differ (that is what Doppel measures); shapes must not.
Usage: .venv/bin/python scripts/shape_check.py [v1_url] [v2_url]
"""

from __future__ import annotations

import sys
from typing import Any

import httpx


def shape(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if v is None:
        return "null"
    return type(v).__name__


def calls(c: httpx.Client) -> list[tuple[str, Any]]:
    out = [("POST /reset", c.post("/reset").json())]
    out.append(("POST /customers", c.post("/customers", json={"name": "Shape Check", "state": "Kerala"}).json()))
    inv = c.post("/invoices", json={"customer_id": 1, "items": [{"sku": "SKU-TEA", "qty": 2}, {"sku": "SKU-CABLE", "qty": 1}],
                                    "coupon_pct": 10, "due_date": "2026-12-06"}).json()
    out.append(("POST /invoices", inv))
    out.append(("GET /invoices/{id}", c.get(f"/invoices/{inv['id']}").json()))
    out.append(("POST /invoices/{id}/refund", c.post(f"/invoices/{inv['id']}/refund", json={"sku": "SKU-TEA", "qty": 1}).json()))
    out.append(("POST /invoices/{id}/pay", c.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-09"}).json()))
    out.append(("GET /invoices/999 (404)", c.get("/invoices/999").json()))
    out.append(("POST /invoices/{id}/pay again (400)", c.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-09"}).json()))
    return out


def main() -> int:
    v1_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
    v2_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8002"
    with httpx.Client(base_url=v1_url) as a, httpx.Client(base_url=v2_url) as b:
        ra, rb = calls(a), calls(b)
    failures = 0
    for (name, x), (_, y) in zip(ra, rb):
        same = shape(x) == shape(y)
        failures += not same
        print(f"{'OK  ' if same else 'FAIL'} {name}")
        if not same:
            print(f"     v1: {shape(x)}\n     v2: {shape(y)}")
    print("shapes identical" if not failures else f"{failures} endpoint(s) differ in shape")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
