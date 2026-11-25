"""Business rules of the legacy system (the reference behaviour)."""

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path):
    os.environ["BILLING_DB"] = str(tmp_path / "test.db")
    import main

    importlib.reload(main)
    with TestClient(main.app) as c:
        c.post("/reset")
        yield c


def invoice(c, customer_id=1, items=None, coupon=0, due="2026-12-08"):
    body = {"customer_id": customer_id, "items": items or [{"sku": "SKU-TEA", "qty": 2}], "due_date": due}
    if coupon:
        body["coupon_pct"] = coupon
    r = c.post("/invoices", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_same_state_splits_cgst_and_sgst(client):
    inv = invoice(client, customer_id=1)  # Maharashtra, like the seller
    assert inv["interstate"] is False
    assert inv["subtotal"] == 480.0
    assert inv["tax_total"] == 24.0
    assert (inv["cgst"], inv["sgst"], inv["igst"]) == (12.0, 12.0, 0.0)
    assert inv["total"] == 504.0


def test_other_state_charges_igst(client):
    inv = invoice(client, customer_id=5)  # Kerala
    assert inv["interstate"] is True
    assert (inv["cgst"], inv["sgst"], inv["igst"]) == (0.0, 0.0, 24.0)


def test_gst_is_rounded_once_on_the_invoice_total(client):
    # Three lines of 99.99 at 18%: 17.9982 each. Rounded once: 53.99. Rounded per line it would be 54.00.
    inv = invoice(client, items=[{"sku": "SKU-CABLE", "qty": 1}, {"sku": "CUSTOM-A", "qty": 1, "unit_price": 99.99, "gst_rate": 18},
                                 {"sku": "CUSTOM-B", "qty": 1, "unit_price": 99.99, "gst_rate": 18}])
    assert inv["tax_total"] == 53.99


def test_coupon_is_applied_after_tax(client):
    inv = invoice(client, items=[{"sku": "SKU-LAMP", "qty": 1}], coupon=10)  # 1250 at 12%
    assert inv["tax_total"] == 150.0  # tax on the full price
    assert inv["discount"] == 140.0  # 10% of 1400
    assert inv["total"] == 1260.0


def test_late_payment_adds_two_percent(client):
    inv = invoice(client, due="2026-12-08")  # a Tuesday
    paid = client.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-10"}).json()
    assert paid["late_fee"] == 10.08
    assert paid["amount_paid"] == 514.08


def test_on_time_payment_has_no_late_fee(client):
    inv = invoice(client, due="2026-12-08")
    paid = client.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-08"}).json()
    assert paid["late_fee"] == 0.0


def test_no_late_fee_when_due_date_is_a_sunday(client):
    inv = invoice(client, due="2026-12-06")  # a Sunday
    paid = client.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-20"}).json()
    assert paid["late_fee"] == 0.0
    assert paid["amount_paid"] == 504.0


def test_partial_refund_includes_tax(client):
    inv = invoice(client, items=[{"sku": "SKU-PEN", "qty": 3}])  # 120 at 12%
    out = client.post(f"/invoices/{inv['id']}/refund", json={"sku": "SKU-PEN", "qty": 1}).json()
    assert out["refunds"][0]["amount"] == 134.4
    assert out["refunds"][0]["tax"] == 14.4
    assert out["refunded"] == 134.4


def test_refund_with_coupon_takes_the_coupon_off_after_tax(client):
    inv = invoice(client, items=[{"sku": "SKU-PEN", "qty": 3}], coupon=10)
    out = client.post(f"/invoices/{inv['id']}/refund", json={"sku": "SKU-PEN", "qty": 1}).json()
    assert out["refunds"][0]["amount"] == 120.96  # 134.40 - 10%


def test_cannot_refund_more_than_was_bought(client):
    inv = invoice(client, items=[{"sku": "SKU-PEN", "qty": 2}])
    client.post(f"/invoices/{inv['id']}/refund", json={"sku": "SKU-PEN", "qty": 2})
    r = client.post(f"/invoices/{inv['id']}/refund", json={"sku": "SKU-PEN", "qty": 1})
    assert r.status_code == 400


def test_errors(client):
    assert client.get("/invoices/999").status_code == 404
    assert client.post("/invoices", json={"customer_id": 99, "items": [{"sku": "SKU-TEA", "qty": 1}],
                                          "due_date": "2026-12-01"}).status_code == 404
    assert client.post("/invoices", json={"customer_id": 1, "items": [{"sku": "NOPE", "qty": 1}],
                                          "due_date": "2026-12-01"}).status_code == 400
    inv = invoice(client)
    client.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-01"})
    assert client.post(f"/invoices/{inv['id']}/pay", json={"paid_on": "2026-12-01"}).status_code == 400


def test_reset_restores_seed_data(client):
    invoice(client)
    client.post("/customers", json={"name": "X", "state": "Goa"})
    assert client.post("/reset").json() == {"ok": True, "customers": 10, "products": 15}
    assert client.get("/invoices/1").status_code == 404
