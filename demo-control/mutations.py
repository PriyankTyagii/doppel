"""The break-it-live menu. Each mutation is one reversible, single-line edit to billing-v2 source."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Mutation:
    id: str
    title: str
    description: str
    file: str  # relative to billing-v2/
    find: str
    replace: str
    changes_endpoints: bool = False
    # Words the Doppel explanation must contain to count as naming the right rule (any one of each list).
    expect_keywords: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("expect_keywords")
        return d


MUTATIONS: list[Mutation] = [
    Mutation(
        id="gst_category",
        title="Stationery GST 12% -> 18%",
        description="Moves the stationery category (pens, notebooks) from the 12% GST slab to 18%.",
        file="src/seed.ts",
        find="  stationery: 12,",
        replace="  stationery: 18,",
        expect_keywords=[["stationery"]],
    ),
    Mutation(
        id="late_fee",
        title="Late fee 2% -> 2.5%",
        description="Raises the late-payment fee from 2% to 2.5% of the invoice total.",
        file="src/tax.ts",
        find="export const LATE_FEE_PCT = 2;",
        replace="export const LATE_FEE_PCT = 2.5;",
        expect_keywords=[["late fee", "late_fee", "late-fee", "late_fee_pct"], ["2.5"]],
    ),
    Mutation(
        id="coupon_cap",
        title="Cap coupons at 15%",
        description="Silently limits any coupon above 15% to 15%.",
        file="src/invoices.ts",
        find="  const couponPct = Math.trunc(input.coupon_pct ?? 0);",
        replace="  const couponPct = Math.min(Math.trunc(input.coupon_pct ?? 0), 15);",
        expect_keywords=[["coupon"], ["15", "cap"]],
    ),
    Mutation(
        id="telangana",
        title="Telangana billed as same-state",
        description="Treats Telangana like Maharashtra: CGST + SGST instead of IGST.",
        file="src/tax.ts",
        find="export const SAME_STATE = new Set([SELLER_STATE]);",
        replace='export const SAME_STATE = new Set([SELLER_STATE, "Telangana"]);',
        expect_keywords=[["telangana"]],
    ),
    Mutation(
        id="refund_round_down",
        title="Round refunds down",
        description="Rounds the GST on refunds down to the paisa instead of to the nearest paisa.",
        file="src/tax.ts",
        find="  const tax = percentOf(taxable, line.gstRate);",
        replace="  const tax = Math.floor((taxable * line.gstRate) / 100);",
        expect_keywords=[["refund"], ["floor", "round"]],
    ),
]

BY_ID = {m.id: m for m in MUTATIONS}
