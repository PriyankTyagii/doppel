"""The comparator ignores harmless differences and reports real ones; runs are classified against the last run."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compare import compare_outputs, impact, normalise  # noqa: E402
from pipeline import _inr, classify, group_impact, signature  # noqa: E402


def inv(**over):
    base = {"id": 1, "customer_id": 1, "state": "Kerala", "total": 504.0, "tax_total": 24.0, "late_fee": 0.0,
            "refunded": 0.0, "items": [{"sku": "SKU-TEA", "qty": 2}], "created_at": "2026-11-25T10:00:00Z",
            "refunds": []}
    base.update(over)
    return base


def test_ignores_ids_timestamps_key_order_and_float_noise():
    a = inv()
    b = dict(reversed(list(inv(id=77, customer_id=12, created_at="2030-01-01T00:00:00Z", total=504.004).items())))
    assert compare_outputs([a], [b], ["get_invoice"]) == []


def test_ignores_int_vs_float_for_the_same_number():
    assert compare_outputs([{"late_fee": 0.0}], [{"late_fee": 0}], ["pay_invoice"]) == []


def test_nested_ids_and_timestamps_are_ignored():
    a = inv(refunds=[{"id": 1, "sku": "SKU-TEA", "amount": 252.0, "created_at": "x"}])
    b = inv(refunds=[{"id": 9, "sku": "SKU-TEA", "amount": 252.0, "created_at": "y"}])
    assert compare_outputs([a], [b], ["refund_invoice"]) == []


def test_reports_real_money_difference_with_rupee_delta():
    diffs = compare_outputs([inv()], [inv(late_fee=10.08, total=504.0)], ["pay_invoice"])
    assert len(diffs) == 1
    d = diffs[0]
    assert d.path == "1:pay_invoice.late_fee"
    assert (d.v1, d.v2, d.delta) == (0, 10.08, 10.08)
    assert d.field == "late_fee"


def test_one_paisa_is_a_real_difference():
    assert len(compare_outputs([inv()], [inv(tax_total=24.01)], ["get_invoice"])) == 1


def test_missing_keys_and_errors_are_reported():
    diffs = compare_outputs([inv()], [{"error": 404, "detail": "invoice not found"}], ["get_invoice"])
    assert diffs, "an error on one side only must be a mismatch"


def test_list_fields_get_a_stable_field_name():
    a = inv(refunds=[{"sku": "SKU-TEA", "tax": 1.0, "amount": 21.0}])
    b = inv(refunds=[{"sku": "SKU-TEA", "tax": 0.99, "amount": 20.99}])
    fields = {d.field for d in compare_outputs([a], [b], ["refund_invoice"])}
    assert fields == {"refunds[].tax", "refunds[].amount"}


def test_normalise_drops_ids_recursively():
    assert normalise({"id": 1, "x": {"invoice_id": 2, "y": 1.0}}) == {"x": {"y": 1}}


def test_signature_drops_derived_totals_and_merges_gst_split():
    diffs = [{"field": f} for f in ("cgst", "sgst", "tax_total", "total")]
    assert signature(diffs) == ["gst_split", "tax_total"]
    assert signature([{"field": "total"}]) == ["total"]


def test_impact_separates_bill_from_tax():
    i = impact([inv()], [inv(total=503.99, tax_total=23.99)])
    assert i == {"bill_delta": -0.01, "tax_delta": -0.01, "direction": "undercharged"}
    i = impact([inv()], [inv(tax_total=20.0)])
    assert i["bill_delta"] == 0.0 and i["tax_delta"] == -4.0 and i["direction"] == "none"


def _result(match, diffs=()):
    return {"match": match, "diffs": list(diffs)}


def test_classify_statuses():
    d1 = {"path": "1:pay_invoice.late_fee", "v2": 10.08}
    d2 = {"path": "1:pay_invoice.late_fee", "v2": 12.6}
    assert classify(_result(False, [d1]), None) == "NEW"
    assert classify(_result(True), None) == "OK"
    assert classify(_result(False, [d1]), _result(True)) == "NEW"
    assert classify(_result(True), _result(False, [d1])) == "FIXED"
    assert classify(_result(False, [d1]), _result(False, [d1])) == "UNCHANGED"
    assert classify(_result(False, [d2]), _result(False, [d1])) == "NEW", "a changed v2 value is a new break"


def test_group_impact_and_projection():
    rs = [{"impact": {"bill_delta": 10.0, "tax_delta": 0.0}}, {"impact": {"bill_delta": -2.0, "tax_delta": -1.0}},
          {"impact": {"bill_delta": 0.0, "tax_delta": 5.0}}]
    g = group_impact(rs, total_scenarios=60, monthly_volume=100_000)
    assert g["invoices_affected"] == 3
    assert g["rupees_wrong"] == 12.0
    assert (g["overcharged"], g["undercharged"], g["tax_only"]) == (1, 1, 1)
    assert g["tax_misreported"] == 6.0
    assert g["projected_monthly_invoices"] == 5000
    assert g["projected_monthly_rupees"] == 20000.0


def test_indian_number_format():
    assert _inr(100000) == "1,00,000"
    assert _inr(12345678.4) == "1,23,45,678"
    assert _inr(999) == "999"
