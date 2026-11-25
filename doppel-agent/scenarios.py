"""Deterministic business scenarios (seed 42).

A scenario is a short sequence of logical tool calls run on a freshly reset system. Later steps can
refer to the output of earlier ones with ``"$name.field"`` placeholders (e.g. ``"$inv.id"``).

Mix (60 scenarios): the 50 core scenarios from the plan, plus 10 "mutation guard" scenarios that make
sure each of the five break-it-live mutations is caught.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from typing import Any

SEED = 42
STATES = ["Maharashtra", "Karnataka", "Kerala", "Delhi", "Tamil Nadu"]
# Seed customer ids by state (two per state, see billing seed data).
CUSTOMERS_BY_STATE = {
    "Maharashtra": [1, 2], "Karnataka": [3, 4], "Kerala": [5, 6], "Delhi": [7, 8], "Tamil Nadu": [9, 10],
}
# Catalog items whose tax always comes out in whole paise.
ROUND_PRICED = ["SKU-TEA", "SKU-RICE", "SKU-OIL", "SKU-SOAP", "SKU-PEN", "SKU-BOOK", "SKU-BAG",
                "SKU-MOUSE", "SKU-LAMP", "SKU-GHEE", "SKU-SHOE", "SKU-TOWEL"]
STATIONERY = ["SKU-PEN", "SKU-BOOK"]
# Odd prices: per-line tax has fractions of a paisa.
ODD_PRICED = ["SKU-CABLE", "SKU-CHARGER", "SKU-SPICE"]
ODD_CUSTOM = [
    {"sku": "CUSTOM-BRUSH", "unit_price": 59.99, "gst_rate": 12},
    {"sku": "CUSTOM-CANDLE", "unit_price": 74.95, "gst_rate": 18},
    {"sku": "CUSTOM-JAR", "unit_price": 129.99, "gst_rate": 12},
    {"sku": "CUSTOM-SNACK", "unit_price": 33.33, "gst_rate": 5},
]
ODD_BASKETS = [
    [("SKU-CHARGER", 3), ("CUSTOM-CANDLE", 2), ("SKU-CABLE", 3)],
    [("SKU-CHARGER", 3), ("CUSTOM-SNACK", 1), ("SKU-SPICE", 2), ("CUSTOM-BRUSH", 1)],
    [("SKU-SPICE", 1), ("SKU-CABLE", 1), ("CUSTOM-JAR", 1)],
    [("SKU-CABLE", 3), ("CUSTOM-CANDLE", 3), ("SKU-SPICE", 1), ("CUSTOM-SNACK", 3)],
    [("CUSTOM-CANDLE", 2), ("SKU-CABLE", 3), ("CUSTOM-SNACK", 1), ("SKU-SPICE", 3)],
    [("SKU-SPICE", 4), ("CUSTOM-BRUSH", 2), ("SKU-SOAP", 3)],
    [("SKU-CHARGER", 3), ("SKU-CABLE", 3), ("CUSTOM-BRUSH", 2)],
    [("SKU-CHARGER", 1), ("CUSTOM-JAR", 1), ("CUSTOM-CANDLE", 1)],
]
BASE_DATE = dt.date(2026, 12, 1)


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    save_as: str | None = None


@dataclass
class Scenario:
    id: str
    kind: str
    summary: str
    steps: list[Step]
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scenario":
        return cls(id=d["id"], kind=d["kind"], summary=d["summary"],
                   steps=[Step(**s) for s in d["steps"]], tags=d.get("tags", []))

    def fingerprint(self) -> str:
        """Stable hash of what the scenario does; keys the billing-v1 result cache."""
        body = json.dumps([asdict(s) for s in self.steps], sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()[:16]


def _date(rng: random.Random, sunday: bool | None = None) -> dt.date:
    d = BASE_DATE + dt.timedelta(days=rng.randint(0, 45))
    if sunday is True:
        d += dt.timedelta(days=(6 - d.weekday()) % 7)
    elif sunday is False and d.weekday() == 6:
        d += dt.timedelta(days=1)
    return d


def _fmt(d: dt.date) -> str:
    return d.isoformat()


def _label(d: dt.date) -> str:
    return d.strftime("%a %d %b")


def _items(rng: random.Random, pool: list[str], n: int, qty=(1, 4)) -> list[dict[str, Any]]:
    skus = rng.sample(pool, n)
    return [{"sku": s, "qty": rng.randint(*qty)} for s in skus]


def _odd_item(sku: str, qty: int) -> dict[str, Any]:
    custom = next((c for c in ODD_CUSTOM if c["sku"] == sku), None)
    return dict(custom, qty=qty) if custom else {"sku": sku, "qty": qty}


def _invoice_step(customer_id: int, items, due: dt.date, coupon: int = 0) -> Step:
    args: dict[str, Any] = {"customer_id": customer_id, "items": items, "due_date": _fmt(due)}
    if coupon:
        args["coupon_pct"] = coupon
    return Step("create_invoice", args, save_as="inv")


def _customer(rng: random.Random, state: str) -> int:
    return rng.choice(CUSTOMERS_BY_STATE[state])


def generate(seed: int = SEED) -> list[Scenario]:
    rng = random.Random(seed)
    out: list[Scenario] = []

    def add(kind: str, summary: str, steps: list[Step], tags: list[str] | None = None) -> None:
        out.append(Scenario(f"S{len(out) + 1:02d}", kind, summary, steps, tags or []))

    # 20 plain invoices across 5 states; about half are paid on time.
    for i in range(20):
        state = STATES[i % 5]
        n = rng.randint(1, 3)
        items = _items(rng, ROUND_PRICED, n)
        due = _date(rng, sunday=True if i in (6, 13) else None)
        steps = [_invoice_step(_customer(rng, state), items, due)]
        paid = ""
        if i % 2 == 0:
            on = due - dt.timedelta(days=rng.randint(0, 5))
            steps.append(Step("pay_invoice", {"id": "$inv.id", "paid_on": _fmt(on)}))
            paid = ", paid on time"
        steps.append(Step("get_invoice", {"id": "$inv.id"}))
        where = "same-state" if state == "Maharashtra" else "inter-state"
        add("plain", f"{state} customer, {n} item{'s' if n > 1 else ''}, {where}{paid}", steps)

    # 8 invoices with 3+ lines at odd prices. Baskets are fixed (a sample of real-looking legacy
    # invoices) so the run is stable; state and dates still come from the seed.
    for basket in ODD_BASKETS:
        state = rng.choice(STATES)
        items = [_odd_item(sku, qty) for sku, qty in basket]
        due = _date(rng, sunday=False)
        steps = [_invoice_step(_customer(rng, state), items, due), Step("get_invoice", {"id": "$inv.id"})]
        add("odd_prices", f"{state} customer, {len(items)} items at odd prices", steps, ["rounding"])

    # 2 invoices with a coupon.
    for i in range(2):
        state = rng.choice(STATES)
        pct = rng.choice([5, 10, 15])
        items = _items(rng, ROUND_PRICED, rng.randint(2, 3))
        due = _date(rng, sunday=False)
        steps = [_invoice_step(_customer(rng, state), items, due, coupon=pct),
                 Step("get_invoice", {"id": "$inv.id"})]
        add("coupon", f"{state} customer, {pct}% coupon, {len(items)} items", steps, ["coupon"])

    # 10 invoices paid late; 4 of them were due on a Sunday.
    for i in range(10):
        state = rng.choice(STATES)
        sunday = i < 4
        items = _items(rng, ROUND_PRICED, rng.randint(1, 3))
        due = _date(rng, sunday=sunday if sunday else False)
        late = rng.randint(1, 15)
        steps = [_invoice_step(_customer(rng, state), items, due),
                 Step("pay_invoice", {"id": "$inv.id", "paid_on": _fmt(due + dt.timedelta(days=late))})]
        add("late", f"{state} customer, paid {late} day{'s' if late > 1 else ''} late (due {_label(due)})", steps,
            ["late", "sunday"] if sunday else ["late"])

    # 10 invoices with a partial refund.
    for i in range(10):
        state = rng.choice(STATES)
        items = _items(rng, ROUND_PRICED, rng.randint(2, 3), qty=(2, 5))
        due = _date(rng, sunday=False)
        target = rng.choice(items)
        back = rng.randint(1, target["qty"] - 1)
        steps = [_invoice_step(_customer(rng, state), items, due)]
        if i % 2 == 0:
            steps.append(Step("pay_invoice", {"id": "$inv.id", "paid_on": _fmt(due)}))
        steps.append(Step("refund_invoice", {"id": "$inv.id", "sku": target["sku"], "qty": back}))
        add("refund", f"{state} customer returns {back} of {target['qty']} x {target['sku']}", steps, ["refund"])

    out.extend(_mutation_guards(rng, start=len(out) + 1))
    return out


def _mutation_guards(rng: random.Random, start: int) -> list[Scenario]:
    """Two scenarios per break-it-live mutation, so every mutation is caught."""
    out: list[Scenario] = []

    def add(kind: str, summary: str, steps: list[Step], tags: list[str]) -> None:
        out.append(Scenario(f"S{start + len(out):02d}", kind, summary, steps, ["guard", *tags]))

    # 1. GST rate for a product category (stationery).
    for state in ("Maharashtra", "Kerala"):
        items = [{"sku": s, "qty": rng.randint(2, 6)} for s in STATIONERY]
        due = _date(rng, sunday=False)
        add("guard_gst_category", f"{state} customer buys stationery",
            [_invoice_step(_customer(rng, state), items, due), Step("get_invoice", {"id": "$inv.id"})],
            ["gst_category"])

    # 2. Late fee percentage.
    for state in ("Delhi", "Maharashtra"):
        items = _items(rng, ROUND_PRICED, 2)
        due = _date(rng, sunday=False)
        add("guard_late_fee", f"{state} customer, paid 10 days late (due {_label(due)})",
            [_invoice_step(_customer(rng, state), items, due),
             Step("pay_invoice", {"id": "$inv.id", "paid_on": _fmt(due + dt.timedelta(days=10))})],
            ["late"])

    # 3. Coupon above 15%.
    for state, pct in (("Karnataka", 20), ("Maharashtra", 25)):
        items = _items(rng, ROUND_PRICED, 2)
        due = _date(rng, sunday=False)
        add("guard_coupon_cap", f"{state} customer, {pct}% festival coupon",
            [_invoice_step(_customer(rng, state), items, due, coupon=pct), Step("get_invoice", {"id": "$inv.id"})],
            ["coupon"])

    # 4. A Telangana customer (inter-state from Maharashtra: IGST only).
    for name in ("Sai Reddy", "Lakshmi Rao"):
        items = _items(rng, ROUND_PRICED, 2)
        due = _date(rng, sunday=False)
        add("guard_telangana", "New Telangana customer, 2 items",
            [Step("create_customer", {"name": name, "state": "Telangana"}, save_as="cust"),
             _invoice_step("$cust.id", items, due),  # type: ignore[arg-type]
             Step("get_invoice", {"id": "$inv.id"})],
            ["state"])

    # 5. Refund rounding (odd price, so the refund's tax has fractions of a paisa).
    for sku in ("SKU-CABLE", "SKU-CHARGER"):
        state = rng.choice(STATES)
        items = [{"sku": sku, "qty": 3}, {"sku": rng.choice(ROUND_PRICED), "qty": 1}]
        due = _date(rng, sunday=False)
        add("guard_refund_rounding", f"{state} customer returns 1 of 3 x {sku}",
            [_invoice_step(_customer(rng, state), items, due),
             Step("refund_invoice", {"id": "$inv.id", "sku": sku, "qty": 1})],
            ["refund"])
    return out


if __name__ == "__main__":
    for s in generate():
        print(s.id, s.kind.ljust(22), s.summary)
