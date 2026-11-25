"""Deterministic parts of the explainer: diff parsing, line pinning, fallback, and merging fresh breaks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from explain import added_lines, fallback_explanation, pin_changed_line  # noqa: E402
from pipeline import _merge_same_change  # noqa: E402

DIFF = """diff --git a/billing-v2/src/tax.ts b/billing-v2/src/tax.ts
--- a/billing-v2/src/tax.ts
+++ b/billing-v2/src/tax.ts
@@ -2,5 +2,5 @@ import x

 export const SELLER_STATE = "Maharashtra";
-export const LATE_FEE_PCT = 2;
+export const LATE_FEE_PCT = 2.5;
 export const GST_RATES = [5, 12, 18] as const;
@@ -60,3 +60,3 @@ export function computeRefund(
   const gross = qty * line.unitPrice;
-  const tax = percentOf(taxable, line.gstRate);
+  const tax = Math.floor((taxable * line.gstRate) / 100);
"""


def test_added_lines_have_current_file_line_numbers():
    assert added_lines(DIFF) == [
        ("billing-v2/src/tax.ts", 4, "export const LATE_FEE_PCT = 2.5;"),
        ("billing-v2/src/tax.ts", 61, "  const tax = Math.floor((taxable * line.gstRate) / 100);"),
    ]


def test_pin_changed_line_corrects_the_line_number():
    e = pin_changed_line({"changed_line": "billing-v2/src/tax.ts:7  export const LATE_FEE_PCT = 2.5;"}, DIFF)
    assert e["changed_line"] == "billing-v2/src/tax.ts:4  export const LATE_FEE_PCT = 2.5;"
    assert e["recent_change"] is True


def test_pin_changed_line_leaves_unmatched_quotes_alone():
    e = pin_changed_line({"changed_line": "", "recent_change": False}, DIFF)
    assert e == {"changed_line": "", "recent_change": False}


def test_fallback_never_claims_a_root_cause():
    e = fallback_explanation({"fields": ["late_fee"]}, DIFF, "no credentials")
    assert e["source"] == "fallback" and e["rule"] == "unknown" and e["v2_line"] == 0
    assert "LATE_FEE_PCT = 2.5" in e["changed_line"]


def _g(key, origin, ids, loc=None):
    e = {"recent_change": bool(loc)}
    if loc:
        e["changed_file"], e["changed_line_no"] = loc
    return {"key": key, "origin": origin, "status": "NEW" if origin != "known" else "UNCHANGED",
            "fields": [key.split(":")[1]], "scenario_ids": ids, "explanation": e}


def test_fresh_breaks_from_one_changed_line_become_one_card():
    groups = {g["key"]: g for g in [
        _g("changed:late_fee", "changed", ["S31"], ("tax.ts", 4)),
        _g("new:late_fee", "new", ["S35", "S36"], ("tax.ts", 4)),
        _g("known:discount", "known", ["S29"]),
    ]}
    out = _merge_same_change(groups)
    assert set(out) == {"new:late_fee", "known:discount"}
    assert out["new:late_fee"]["scenario_ids"] == ["S35", "S36", "S31"]
    assert out["new:late_fee"]["merged_from"] == ["new:late_fee", "changed:late_fee"]


def test_explainer_falls_back_when_no_key_is_configured(monkeypatch):
    import asyncio

    import explain

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = asyncio.run(explain.explain_groups([{"fields": ["late_fee"], "scenario_ids": ["S1"]}], {"S1": {}}, DIFF))
    assert out[0]["source"] == "fallback"
    assert "GROQ_API_KEY" in out[0]["explanation"]
