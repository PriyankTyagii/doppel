"""The three planted differences exist, and the scenario mix scores exactly what the demo needs.

Starts its own billing-v1 and billing-v2 on spare ports with throwaway databases.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
ROOT = HERE.parent.parent

from backends import HttpBackend  # noqa: E402
from compare import compare_outputs  # noqa: E402
from runner import run_all  # noqa: E402
from scenarios import generate  # noqa: E402

V1_PORT, V2_PORT = 8101, 8102


def _wait(url: str, proc: subprocess.Popen, timeout: float = 30) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"{url} exited early")
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{url} did not start")


@pytest.fixture(scope="module")
def apps(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("dbs")
    v1 = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(V1_PORT)],
                          cwd=ROOT / "billing-v1", env={**os.environ, "BILLING_DB": str(tmp / "v1.db")},
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    v2 = subprocess.Popen([str(ROOT / "billing-v2/node_modules/.bin/tsx"), "src/server.ts"], cwd=ROOT / "billing-v2",
                          env={**os.environ, "PORT": str(V2_PORT), "BILLING_DB": str(tmp / "v2.db")},
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait(f"http://localhost:{V1_PORT}", v1)
        _wait(f"http://localhost:{V2_PORT}", v2)
        yield f"http://localhost:{V1_PORT}", f"http://localhost:{V2_PORT}"
    finally:
        v1.terminate()
        v2.terminate()


def both(apps, fn):
    out = []
    for url in apps:
        with httpx.Client(base_url=url) as c:
            c.post("/reset")
            out.append(fn(c))
    return out


def test_gst_rounding_differs(apps):
    items = [{"sku": "SKU-CABLE", "qty": 1}, {"sku": "X1", "qty": 1, "unit_price": 99.99, "gst_rate": 18},
             {"sku": "X2", "qty": 1, "unit_price": 99.99, "gst_rate": 18}]
    v1, v2 = both(apps, lambda c: c.post("/invoices", json={"customer_id": 1, "items": items,
                                                            "due_date": "2026-12-08"}).json())
    assert v1["tax_total"] == 53.99  # rounded once
    assert v2["tax_total"] == 54.00  # rounded per line


def test_sunday_late_fee_differs(apps):
    def run(c):
        inv = c.post("/invoices", json={"customer_id": 1, "items": [{"sku": "SKU-TEA", "qty": 2}],
                                        "due_date": "2026-12-06"}).json()
        return c.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-10"}).json()

    v1, v2 = both(apps, run)
    assert v1["late_fee"] == 0.0  # waived: due on a Sunday
    assert v2["late_fee"] == 10.08


def test_weekday_late_fee_matches(apps):
    def run(c):
        inv = c.post("/invoices", json={"customer_id": 1, "items": [{"sku": "SKU-TEA", "qty": 2}],
                                        "due_date": "2026-12-08"}).json()
        return c.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-10"}).json()

    v1, v2 = both(apps, run)
    assert v1["late_fee"] == v2["late_fee"] == 10.08


def test_coupon_order_differs(apps):
    v1, v2 = both(apps, lambda c: c.post("/invoices", json={"customer_id": 1, "items": [{"sku": "SKU-LAMP", "qty": 1}],
                                                            "coupon_pct": 10, "due_date": "2026-12-08"}).json())
    assert v1["tax_total"] == 150.0  # GST on the full price, coupon after tax
    assert v2["tax_total"] == 135.0  # coupon first, then GST
    assert v1["total"] == v2["total"]  # the customer pays the same; the GST filed differs


def test_scenario_mix_scores_82_percent(apps):
    async def go():
        v1, v2 = HttpBackend("billing_v1", apps[0]), HttpBackend("billing_v2", apps[1])
        await v1.connect()
        await v2.connect()
        bad = {}
        async for r in run_all(v1, v2, generate()):
            sc = r["scenario"]
            if compare_outputs(r["v1"], r["v2"], [s.tool for s in sc.steps]):
                bad[sc.id] = sc.kind
        await v1.close()
        await v2.close()
        return bad

    bad = asyncio.run(go())
    core = {k: v for k, v in bad.items() if not v.startswith("guard_")}
    assert len(core) == 9, f"core 50 should have 9 mismatches (82%), got {core}"
    assert len(bad) == 11, f"all 60 should have 11 mismatches (82%), got {bad}"
    assert sorted(core.values()) == sorted(["odd_prices"] * 3 + ["coupon"] * 2 + ["late"] * 4)
