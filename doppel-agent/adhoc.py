"""Free-form mode: a judge describes a scenario in plain English; an LLM turns it into tool calls."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from backends import TOOL_DESCRIPTIONS
import _paths  # noqa: F401
import llm
from scenarios import CUSTOMERS_BY_STATE, Scenario, Step

ToolName = Literal["create_customer", "create_invoice", "get_invoice", "pay_invoice", "refund_invoice"]

CATALOG = """SKU-TEA Assam tea 500g Rs240 5% | SKU-RICE Basmati rice 5kg Rs650 5% | SKU-OIL Groundnut oil 1L Rs180 5%
SKU-SOAP Sandal soap Rs45 18% | SKU-PEN Gel pen pack Rs120 12% | SKU-BOOK Notebook A4 Rs85 12%
SKU-BAG Laptop bag Rs1499 18% | SKU-MOUSE Wireless mouse Rs799 18% | SKU-CABLE USB-C cable Rs99.99 18%
SKU-LAMP Desk lamp Rs1250 12% | SKU-GHEE Desi ghee 1L Rs620 12% | SKU-SHOE Running shoes Rs2999 18%
SKU-TOWEL Bath towel Rs349.50 12% | SKU-CHARGER Phone charger Rs149.99 18% | SKU-SPICE Garam masala Rs19.99 5%"""


class PlannedStep(BaseModel):
    tool: ToolName
    args_json: str = Field(description="The tool arguments as a JSON object string.")
    save_as: str = Field(description="Name to save this step's output under (e.g. 'inv', 'cust'), or empty.")


class Plan(BaseModel):
    summary: str = Field(description="One-line restatement of the scenario, e.g. 'Kerala customer, 10% coupon, returns 1 of 3'.")
    steps: list[PlannedStep]
    assumptions: str = Field(description="Any detail you had to choose because the request did not say.")


SYSTEM = f"""You turn a plain-English billing scenario into a sequence of tool calls for a billing API.
The system is reset to seed data before your steps run.

Tools:
{chr(10).join(f"- {k}: {v}" for k, v in TOOL_DESCRIPTIONS.items() if k != "reset")}

Seed customers by state (customer ids): {json.dumps(CUSTOMERS_BY_STATE)}. The seller is in Maharashtra.
For any other state, create a customer first and use "$cust.id" as customer_id.
Catalog (sku, name, price, GST):
{CATALOG}
Items may omit unit_price and gst_rate to use the catalog price.

Later steps can refer to earlier outputs with "$<save_as>.<field>", e.g. "$inv.id".
Dates are YYYY-MM-DD; today is 2026-12-01. Always end by reading the invoice (get_invoice) unless the last step
already returns it (pay_invoice and refund_invoice return the invoice). Keep it to the steps the scenario needs."""


async def plan_scenario(text: str) -> tuple[Scenario, dict[str, Any]]:
    try:
        plan = await llm.complete_json(SYSTEM, text, Plan, timeout=60)
    except llm.LLMError as exc:
        raise ValueError(f"could not plan that scenario: {exc}") from exc
    steps = []
    for s in plan.steps:
        try:
            args = json.loads(s.args_json or "{}")
        except ValueError as exc:
            raise ValueError(f"planner returned invalid JSON args for {s.tool}: {s.args_json}") from exc
        steps.append(Step(s.tool, args, s.save_as or None))
    scenario = Scenario(id="JUDGE", kind="adhoc", summary=plan.summary, steps=steps, tags=["judge"])
    return scenario, {"summary": plan.summary, "assumptions": plan.assumptions, "request": text}
