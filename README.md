# Doppel

**Doppel proves that an AI-rewritten app still behaves exactly like the legacy app it replaces.**
Synapse turns both versions into MCP servers; an agent runs the same business scenarios on both, diffs the
results, and explains every mismatch from the code.

- `billing-v1/`: the legacy system. Python, FastAPI, SQLite, one big terse `main.py`. It is the reference.
- `billing-v2/`: the "AI rewrite". TypeScript, Express, Node's built-in SQLite. Clean code, three planted bugs.
- `doppel-agent/`: the agent. Scenario generator, runner, comparator, Grok explainer, judge mode, SSE API.
- `common/`: shared Python modules: the Grok client and Firebase token verification.
- `demo-control/`: the break-it-live control a human operates. Mutates billing-v2 on stage. The agent never calls it.
- `dashboard/`: React + Vite. Landing page, Firebase sign-in, parity dashboard, business impact, break-it panel, Present mode.

## Setup

Needs Python 3.11 and Node 22+ (for `node:sqlite`).

```bash
make install        # venv, npm packages, and .env / dashboard/.env.local from the templates
```

Fill in two files (both git-ignored):

- `.env`: `XAI_API_KEY` (Grok, from console.x.ai), `FIREBASE_PROJECT_ID`, and `DOPPEL_ADMIN_EMAILS` (verified emails
  allowed to use break-it-live).
- `dashboard/.env.local`: the Firebase web app config (`VITE_FIREBASE_API_KEY`, `..._AUTH_DOMAIN`, `..._PROJECT_ID`,
  `..._APP_ID`) from Project settings → Your apps.

In the Firebase console, enable **Authentication → Sign-in method → Email/Password** and **Google**, and make sure
`localhost` (and your deployed domain) is listed under **Authorized domains**.

Use a Firebase project dedicated to Doppel. Users and sessions belong to a project, so sharing one with another app
lets that app's users call Doppel's API too. Locally the dashboard runs on its own port (5180, `strictPort`) and uses
a named Firebase app, so it never picks up a sign-in from another app on `localhost`.

```bash
make v1             # terminal 1: billing-v1 on :8001
make control        # terminal 2: demo-control on :8090 (starts billing-v2 on :8002)
make agent-http     # terminal 3: Doppel agent on :8000 (use `make agent` once Synapse is set up)
make dashboard      # terminal 4: http://localhost:5180
```

Open http://localhost:5180, sign in, and press **Run parity check**. The gauge fills live and stops at
**82% (49/60 identical)**.

### Authentication

- The dashboard signs in with Firebase (Google or email and password; new email accounts get a verification email).
- Every agent endpoint except `/health` requires a Firebase ID token (`Authorization: Bearer …`). The services
  verify it against Google's public keys for `FIREBASE_PROJECT_ID`: signature, audience, issuer and expiry.
- demo-control (break-it-live) accepts only users whose **verified** email is in `DOPPEL_ADMIN_EMAILS`. Other users
  don't see the Break it tab, and its API answers 403.
- CORS allows only `DOPPEL_ALLOWED_ORIGINS`.
- The services refuse to start without `FIREBASE_PROJECT_ID`. `DOPPEL_AUTH_DISABLED=1` turns auth off for local
  tests and the CLI only.

Command-line alternative: `cd doppel-agent && ../.venv/bin/python cli.py run --mode http --report`.

## Synapse steps (the human runs these)

1. `npm install -g @2ndbrainlabs-ai/synapse-cli` (Node 20+)
2. In `billing-v1/` and `billing-v2/`: `synapse init`, then `synapse build --auto --smart-names`.
   Select only these 6 endpoints:

   | Endpoint | Why Doppel needs it |
   |---|---|
   | `POST /reset` | every scenario starts from identical seed data on both systems |
   | `POST /customers` | scenarios for states outside the seed (e.g. Telangana) |
   | `POST /invoices` | the core of billing: GST, coupons, rounding |
   | `GET /invoices/{id}` | read back the stored invoice |
   | `POST /invoices/{id}/pay` | late fees (and the undocumented Sunday rule) |
   | `POST /invoices/{id}/refund` | partial refunds including tax |

   Do not select `GET /health` (used only by demo-control). Fallback for v1: `synapse build --local`.
3. `cp doppel-agent/mcp.json.example doppel-agent/mcp.json` and paste each printed JSON snippet under
   `billing_v1` and `billing_v2`. Keep secrets as `${ENV}` placeholders; they are expanded from the environment.
4. `make agent` (MCP mode). The dashboard badge changes to "via Synapse MCP".

Doppel maps Synapse's generated tool names to its own (`create_invoice`, `pay_invoice`...) by name and
description. If a name is guessed wrong, pin it in `mcp.json`: `"doppel_tools": {"pay_invoice": "<synapse tool name>"}`.
Check `GET http://localhost:8000/health` to see what was mapped.

> **Check before demo day:** if the hosted Synapse server runs in the cloud, it cannot call `localhost:8001/8002`.
> Then either expose the two apps on a public URL (e.g. a tunnel) or use `synapse build --local` for both.

## How a parity run works

1. `scenarios.py` generates 60 deterministic scenarios (seed 42): 20 plain invoices across 5 states, 8 with
   odd prices, 2 coupons, 10 late payments (4 due on a Sunday), 10 partial refunds, and 10 "mutation guard"
   scenarios (two for each break-it-live mutation).
2. `runner.py` resets both systems and runs each scenario's tool calls on both. **billing-v1 results are cached**
   (keyed by scenario and a hash of the v1 source), so a re-run only calls billing-v2: about 6 seconds for 60
   scenarios over HTTP, explanations included.
3. `compare.py` drops ids and timestamps, sorts keys, ignores float noise under 0.005, then diffs field by field.
4. `pipeline.py` compares with the previous run and marks every mismatch **NEW**, **FIXED** or **UNCHANGED**
   (a known mismatch whose v2 values changed counts as NEW). Fresh breaks are grouped apart from known ones.
5. `explain.py` sends each new group, the numbered source of both systems and **the git diff of billing-v2
   since the last run** to Grok (xAI API, `XAI_MODEL`, schema-constrained JSON output). It returns
   the cause, `file:line` in each system, a one-line explanation, a suggested fix for a human, and the changed
   line, with its line number taken from the diff hunk. Known groups reuse the last explanation. Doppel never
   writes to either repo.
6. Business impact per group: invoices affected, rupees mis-billed (over vs under), GST misreported, and a
   projection to a monthly volume (default 1,00,000 invoices, editable in the dashboard). The projection is
   labelled as a projection from the sample everywhere it appears.

The baseline mismatches are the three planted differences:

| # | Rule | v1 (reference) | v2 (rewrite) | Scenarios |
|---|---|---|---|---|
| 1 | GST rounding | rounded once on the invoice | rounded per line | 3 |
| 2 | Sunday late fee | waived when due on a Sunday (undocumented) | always charged | 4 |
| 3 | Coupon order | coupon after tax | coupon before tax | 4 (incl. 2 guards) |

That is 11/60 (82%). The 50 core scenarios alone are 9/50 (82%), as in the plan.

### Add a scenario

Add a `Step` list in `scenarios.py` (`generate()` or `_mutation_guards()`), using `"$inv.id"` to refer to an
earlier step's output. Run `make test`: `test_scenario_mix_scores_82_percent` tells you if the score moved.
Judges can also type a scenario in plain English in the dashboard ("Kerala customer, 10% coupon, returns 1 of 3 items").

## Live demo runbook

Before going on stage, with all four processes running (see Setup):

1. `git status`: billing-v2 must have no uncommitted changes (demo-control refuses to start a demo otherwise).
2. Sign in, open http://localhost:5180/present (arrow keys move between scenes).
3. On the dashboard, press **Reset baseline** once. This forgets earlier runs and re-calls billing-v1, so the cards read
   "Mismatch found". Expect 82%. Leave it there.

On stage (Present mode scenes):

| Scene | Click / say |
|---|---|
| 1. Headline | "If you switched today: 18% of bills wrong, ~₹1,98,683/month mis-billed and ~₹6,11,800/month GST misreported (projected)." |
| 2. Parity | Gauge at 82%. Optionally press **Run parity check** to show it fill live (about 6s). |
| 3. Findings | Three cards. Headline: **Sunday due-date late-fee waiver missing in v2**, `billing-v1/main.py:229`. |
| 4. Break it | Ask a judge to pick one of the five buttons. Wait for "billing-v2 restarted, healthy after ~0.5s" and "Behaviour-only change: no Synapse rebuild needed". |
| 5. Re-run | Press **Run parity check**. A highlighted **New since last run** card names the changed line, e.g. `billing-v2/src/tax.ts:4 export const LATE_FEE_PCT = 2.5;`. The gauge shows the drop vs the previous run. |
| 6. Report | **Download the parity report** (Markdown). |

What each mutation does to the score (from the acceptance run):

| Mutation | Parity after | NEW card |
|---|---|---|
| Stationery GST 12% -> 18% | 60.0% | `billing-v2/src/seed.ts:19  stationery: 18,` |
| Late fee 2% -> 2.5% | 68.3% | `billing-v2/src/tax.ts:4  export const LATE_FEE_PCT = 2.5;` |
| Cap coupons at 15% | 81.7% (unchanged) | `billing-v2/src/invoices.ts:132` coupon cap |
| Telangana billed as same-state | 78.3% | `billing-v2/src/tax.ts:29` SAME_STATE |
| Round refunds down | 78.3% | `billing-v2/src/tax.ts:67` Math.floor |

"Cap coupons" leaves the percentage at 82% because the scenarios it affects (20% and 25% coupons) already
mismatch on coupon order. Doppel still flags them NEW, because v2's values changed. For the most visible drop,
steer judges to **Stationery GST** or **Late fee**.

**Advanced (hand edit):** in the Break it panel, open "Advanced: edit one line by hand", choose a function
(e.g. `tax.ts · lateFee`), change exactly one line, press **Check** (type check in a scratch copy), then
**Type-check and apply**. If the edited line is a route (`app.get(...)` / `app.post(...)`), demo-control also runs
`synapse build --discover` in billing-v2 and calls the agent's `POST /reconnect`, so Doppel re-lists tools.
Behaviour-only edits skip the rebuild and say so.

**The original live fix (planted bug 2):** edit `lateFee` in `billing-v2/src/tax.ts` to skip Sunday due dates,
optionally add `GET /invoices/:id/breakdown` in `server.ts`, run `synapse build --discover` in `billing-v2/`,
then restart the agent (or call `POST /reconnect` with your token) and run the check. The Sunday finding moves
to "fixed".

### Restore

- Dashboard: **Restore billing-v2** (Break it panel).
- Or: `curl -X POST localhost:8090/restore`.

This discards demo edits in billing-v2 only, switches the repo back from the `live-demo` branch to the branch
the demo started on, forces `billing-v2/` back to the pre-demo commit, restarts billing-v2 and waits for
`/health`. Then run the check again: parity returns to 82%. Restore also discards hand edits you made in billing-v2
during the demo (including a live fix), so commit those first if you want to keep them.

If something goes wrong: `git switch main && git checkout -- billing-v2 && git branch -D live-demo`, then
restart `make control`.

## Tests

```bash
make test         # 48 tests: v1 rules, comparator, explainer helpers, planted differences, 82% mix
make shape        # v1 and v2 return identical JSON shapes on all endpoints
make acceptance   # needs v1, control and agent started with DOPPEL_AUTH_DISABLED=1; real Grok calls (~1.5 min)
```

The acceptance test applies each of the five mutations, re-runs, asserts a NEW mismatch whose explanation names
the rule and the changed line, restores, and asserts parity returns to the previous score.

## Ports

| Service | Port |
|---|---|
| billing-v1 | 8001 |
| billing-v2 (owned by demo-control) | 8002 |
| Doppel agent | 8000 |
| demo-control | 8090 |
| dashboard | 5180 |

Routes: `/` landing, `/login`, `/app` dashboard, `/present` presentation mode (the last two need sign-in).
