# Doppel: proof that a rewrite is still your system

**Problem.** AI can rewrite a legacy system in days, but nobody can prove the rewrite is correct. A 2026 case study
found AI migrations reached only 51% parity on high-level business features. Wrong parity means wrong bills,
wrong tax and lost customers after cutover, and the rules most likely to be lost are the ones nobody wrote down.

**Why Synapse fits.** Doppel needs to call two versions of the same system, written in different languages, in
exactly the same way. Synapse turns each codebase's HTTP API into an MCP server (`billing_v1` from Python/FastAPI,
`billing_v2` from TypeScript/Express), so the agent sees two matching tool sets and never talks to either app
directly. When the rewrite gains an endpoint, `synapse build --discover` updates its server and Doppel re-lists
tools without a restart.

**How it works.**
1. A seeded generator writes 60 business scenarios: states, coupons, Sunday due dates, partial refunds, odd prices.
2. The runner resets both systems and runs each scenario's tool calls on both through MCP. Legacy results are
   cached, since the reference never changes, so a re-run only exercises the rewrite (about 6 seconds).
3. The comparator strips ids, timestamps, key order and float noise, then diffs field by field.
4. Each mismatch is marked NEW, FIXED or UNCHANGED against the previous run. An LLM reads both codebases (with line
   numbers) plus the rewrite's git diff since the last run, and returns the root cause, `file:line` in each system,
   and a suggested fix. The agent is read-only: a human applies fixes.
5. A business view turns diffs into money: invoices affected, rupees over- and under-charged, GST misreported, and
   a labelled projection to 1,00,000 invoices a month.

**Results.** On the baseline the rewrite scores **82% (49/60)**. Doppel finds and explains all three differences
every run: GST rounded per line instead of once (₹0.01 per invoice), coupon applied before tax instead of after
(totals match but the GST filed differs by up to ₹108), and the headline: **v1 silently waives the late fee when the
due date is a Sunday** (`billing-v1/main.py:229`). That rule is undocumented, and the rewrite dropped it.
Projected over 1,00,000 invoices: ~₹1,98,683/month mis-billed and ~₹6,11,800/month GST misreported.

In the break-it-live demo a judge changes the rewrite on stage. In the acceptance run each of five mutations
(category GST rate, late fee %, coupon cap, Telangana as same-state, refund rounding) was caught as a NEW mismatch
whose explanation named the exact changed line, and restoring returned parity to 82%.

**Limits.**
- Parity is only as good as the scenarios. Doppel proves equivalence on what it exercised, not on everything.
  The mutation guards exist because generic scenarios missed some changes.
- Explanations come from a model. Doppel shows the code lines so a human can check them, pins the changed line
  number from the diff rather than trusting the model, and never claims a cause when the explainer is unavailable.
- The rupee projection scales a synthetic sample. It shows the order of magnitude, not a forecast.
- Doppel compares API behaviour. Side effects outside the API (emails, ledgers) need their own endpoints to be checked.
