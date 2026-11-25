"""The explainer only sends the code the scenarios ran, with original line numbers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import code_slice  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def names(defs):
    return {d.name for d in defs}


def test_pay_follows_the_handler_into_the_late_fee_rule_in_both_systems():
    v1 = names(code_slice._closure(code_slice.python_definitions(code_slice.V1_FILE), {"pay_invoice"}))
    v2 = names(code_slice._closure(code_slice.typescript_definitions(code_slice.V2_DIR), {"pay_invoice"}))
    assert {"pay", "hu", "LF", "out"} <= v1
    assert {"payInvoice", "lateFee", "LATE_FEE_PCT", "percentOf"} <= v2


def test_unused_handlers_seed_data_and_types_are_left_out():
    v1 = names(code_slice._closure(code_slice.python_definitions(code_slice.V1_FILE), {"pay_invoice"}))
    v2 = names(code_slice._closure(code_slice.typescript_definitions(code_slice.V2_DIR), {"pay_invoice"}))
    assert not {"refund", "mk_cust", "init", "CUST", "PROD", "PIn"} & v1
    assert not {"refundInvoice", "createCustomer", "PRODUCTS", "CUSTOMERS", "SCHEMA", "InvoiceRow"} & v2


def test_line_numbers_match_the_files():
    text = code_slice.relevant_source({"pay_invoice"})
    main = (ROOT / "billing-v1" / "main.py").read_text().splitlines()
    line = next(l for l in text.splitlines() if "weekday()" in l)
    number, code = int(line[:4]), line[6:]
    assert main[number - 1] == code


def test_slice_is_much_smaller_than_the_codebases():
    full = len((ROOT / "billing-v1" / "main.py").read_text()) + sum(
        len(p.read_text()) for p in (ROOT / "billing-v2" / "src").glob("*.ts"))
    assert len(code_slice.relevant_source({"create_invoice", "get_invoice"})) < 0.6 * full
