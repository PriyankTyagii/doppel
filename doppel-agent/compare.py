"""Normalise two systems' outputs and diff them field by field."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Generated ids and timestamps differ between systems for harmless reasons.
IGNORED_KEYS = {"id", "customer_id", "invoice_id", "refund_id", "created_at", "updated_at", "timestamp"}
FLOAT_TOLERANCE = 0.005
# Fields that hold rupee amounts (used for the rupee difference and business impact).
MONEY_FIELDS = {"subtotal", "cgst", "sgst", "igst", "tax_total", "discount", "total", "late_fee",
                "amount_paid", "refunded", "amount", "tax", "unit_price"}


@dataclass
class FieldDiff:
    path: str
    v1: Any
    v2: Any
    delta: float | None  # v2 - v1 in rupees, for money fields

    @property
    def field(self) -> str:
        """The leaf field name without step or list indices, e.g. ``refunds[].tax``."""
        parts = self.path.split(".")[1:]  # drop the step prefix
        return ".".join(p.split("[")[0] + ("[]" if "[" in p else "") for p in parts) or self.path

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["field"] = self.field
        return d


def normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in sorted(value.items()) if k not in IGNORED_KEYS and not k.endswith("_at")}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[")[0]


def diff(a: Any, b: Any, path: str = "") -> list[FieldDiff]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[FieldDiff] = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a or k not in b:
                out.append(FieldDiff(p, a.get(k, "<missing>"), b.get(k, "<missing>"), None))
            else:
                out.extend(diff(a[k], b[k], p))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        for i in range(max(len(a), len(b))):
            p = f"{path}[{i}]"
            if i >= len(a) or i >= len(b):
                out.append(FieldDiff(p, a[i] if i < len(a) else "<missing>", b[i] if i < len(b) else "<missing>", None))
            else:
                out.extend(diff(a[i], b[i], p))
        return out
    if _is_num(a) and _is_num(b):
        if abs(a - b) < FLOAT_TOLERANCE:
            return []
        delta = round(b - a, 2) if _leaf(path) in MONEY_FIELDS else None
        return [FieldDiff(path, a, b, delta)]
    if a != b:
        return [FieldDiff(path, a, b, None)]
    return []


def compare_outputs(v1_steps: list[Any], v2_steps: list[Any], tools: list[str]) -> list[FieldDiff]:
    """Diffs step-by-step outputs. Paths are prefixed with the step, e.g. ``2:pay_invoice.late_fee``."""
    out: list[FieldDiff] = []
    for i in range(max(len(v1_steps), len(v2_steps))):
        a = normalise(v1_steps[i]) if i < len(v1_steps) else "<missing>"
        b = normalise(v2_steps[i]) if i < len(v2_steps) else "<missing>"
        prefix = f"{i + 1}:{tools[i] if i < len(tools) else 'step'}"
        if isinstance(a, dict) and isinstance(b, dict):
            out.extend(FieldDiff(f"{prefix}.{d.path}", d.v1, d.v2, d.delta) for d in diff(a, b))
        else:
            out.extend(FieldDiff(f"{prefix}.{d.path}" if d.path else prefix, d.v1, d.v2, d.delta) for d in diff(a, b))
    return out


def final_invoice(steps: list[Any]) -> dict[str, Any] | None:
    for out in reversed(steps):
        if isinstance(out, dict) and "total" in out and "items" in out:
            return out
    return None


def customer_bill(inv: dict[str, Any] | None) -> float:
    """What the customer ends up owing/paying: total plus late fee, minus refunds."""
    if not inv:
        return 0.0
    return round(float(inv.get("total", 0)) + float(inv.get("late_fee", 0)) - float(inv.get("refunded", 0)), 2)


def impact(v1_steps: list[Any], v2_steps: list[Any]) -> dict[str, Any]:
    """Business impact of one scenario.

    ``bill_delta``: v2 minus v1 for what the customer ends up paying (total + late fee - refunds).
    ``tax_delta``: v2 minus v1 for the GST on the invoice, i.e. what gets filed with the government.
    """
    a, b = final_invoice(v1_steps), final_invoice(v2_steps)
    bill_delta = round(customer_bill(b) - customer_bill(a), 2)
    tax_delta = round(float((b or {}).get("tax_total", 0)) - float((a or {}).get("tax_total", 0)), 2)
    if abs(bill_delta) < FLOAT_TOLERANCE:
        bill_delta = 0.0
    if abs(tax_delta) < FLOAT_TOLERANCE:
        tax_delta = 0.0
    direction = "overcharged" if bill_delta > 0 else "undercharged" if bill_delta < 0 else "none"
    return {"bill_delta": bill_delta, "tax_delta": tax_delta, "direction": direction}
