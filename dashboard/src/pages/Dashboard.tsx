import { useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { BreakItPanel } from "../components/BreakItPanel";
import { DiffModal } from "../components/DiffModal";
import { FindingCard } from "../components/FindingCard";
import { Gauge } from "../components/Gauge";
import { ResultGrid } from "../components/ResultGrid";
import { TryScenario } from "../components/TryScenario";
import { downloadReport } from "../lib/api";
import { num, rs, rsWhole } from "../lib/format";
import { Link } from "../lib/router";
import { useRun, type RunState } from "../lib/useRun";
import type { FullResult } from "../types";

export function verdict(s: RunState): { text: string; tone: "good" | "bad" | "idle" } {
  const sum = s.run?.summary;
  if (s.running) return { text: "Checking both systems…", tone: "idle" };
  if (!sum) return { text: "No parity check yet.", tone: "idle" };
  if (sum.identical === sum.total) return { text: "Every scenario matches the legacy system. Safe to switch on this evidence.", tone: "good" };
  const imp = sum.impact;
  return {
    text: `If you switched today, ${Math.round(100 - sum.parity_pct)}% of bills would be wrong: about ${rsWhole(
      imp.projected_monthly_rupees * s.scale,
    )} mis-billed and ${rsWhole(imp.projected_monthly_tax * s.scale)} of GST misreported each month (projected).`,
    tone: "bad",
  };
}

function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : new Date(iso).toLocaleDateString();
}

export function Dashboard() {
  const s = useRun();
  const [modal, setModal] = useState<{ id?: string; result?: FullResult } | null>(null);
  const [tab, setTab] = useState<"try" | "break">("try");
  const [reportError, setReportError] = useState("");
  const sum = s.run?.summary;
  const imp = sum?.impact;
  const v = verdict(s);
  const hasRun = Boolean(s.run) || s.running;

  const resetBaseline = () => {
    if (confirm("Start over? This forgets previous runs and calls billing-v1 again, so nothing is marked new or fixed.")) s.start(true);
  };

  return (
    <div className="shell">
      <AppHeader>
        {s.run && (
          <Link href="/present" className="btn btn-sm btn-ghost">
            Present
          </Link>
        )}
      </AppHeader>

      <main className="page">
        <div className="page-head">
          <div>
            <h1>billing v1 → v2 parity</h1>
            <p className="muted">
              Legacy Python service vs its TypeScript rewrite
              {s.me && <> · {s.me.mode === "mcp" ? "via Synapse MCP" : "direct HTTP"}</>}
              {s.total > 0 && <> · {s.total} scenarios</>}
            </p>
          </div>
          <div className="actions">
            {s.run && (
              <>
                <button className="btn btn-ghost" onClick={resetBaseline} disabled={s.running}>
                  Reset baseline
                </button>
                <button
                  className="btn btn-ghost"
                  disabled={s.running}
                  onClick={() => downloadReport().catch((e) => setReportError(e.message))}
                >
                  Download report
                </button>
              </>
            )}
            <button className="btn btn-primary" onClick={() => s.start(false)} disabled={s.running || !s.loaded}>
              {s.running ? (s.explaining ? "Explaining…" : `Running ${s.done}/${s.total || "…"}`) : "Run parity check"}
            </button>
          </div>
        </div>

        {(s.error || reportError) && (
          <p className="alert alert-bad" role="alert">
            {s.error || reportError}
          </p>
        )}
        {s.me && !s.me.llm.configured && (
          <p className="alert">Explanations are off: set XAI_API_KEY for the agent to trace mismatches to code.</p>
        )}
        {s.stale && !s.running && (
          <p className="alert alert-new">billing-v2 changed. Run the check to see what it broke or fixed.</p>
        )}

        {!s.loaded ? (
          <div className="skeleton" aria-busy="true" />
        ) : !hasRun ? (
          <section className="empty">
            <h2>Run your first parity check</h2>
            <p>
              Doppel resets both systems, runs 60 business scenarios on each, and compares every field. Differences are grouped
              and traced to the code. It takes about ten seconds.
            </p>
            <button className="btn btn-primary btn-lg" onClick={() => s.start(false)}>
              Run parity check
            </button>
          </section>
        ) : (
          <>
            <p className={`verdict verdict-${v.tone}`}>{v.text}</p>

            <section className="overview">
              <div className="card gauge-card">
                <Gauge
                  identical={s.identical}
                  done={s.done}
                  total={s.total}
                  running={s.running}
                  previousPct={s.run?.previous_summary?.parity_pct}
                />
                {s.run && !s.running && (
                  <p className="run-meta">
                    {ago(s.run.started_at)} · {s.run.duration_s}s · v2 <code>{s.run.v2_commit.slice(0, 7)}</code>
                    {s.run.previous_summary && (
                      <>
                        <br />
                        {s.run.counts.NEW} new · {s.run.counts.FIXED} fixed · {s.run.counts.UNCHANGED} unchanged
                      </>
                    )}
                  </p>
                )}
              </div>

              <div className="kpis">
                <div className="card kpi">
                  <span className="kpi-label">Bills wrong</span>
                  <span className="kpi-value">{sum && !s.running ? `${sum.total - sum.identical} of ${sum.total}` : "–"}</span>
                  <span className="kpi-sub">in the sample</span>
                </div>
                <div className="card kpi">
                  <span className="kpi-label">Mis-billed</span>
                  <span className="kpi-value">{imp && !s.running ? rsWhole(imp.projected_monthly_rupees * s.scale) : "–"}</span>
                  <span className="kpi-sub">
                    per month, projected{imp && !s.running && <> · {rs(imp.rupees_wrong)} in sample</>}
                  </span>
                  {imp && !s.running && (imp.overcharged > 0 || imp.undercharged > 0) && (
                    <span className="kpi-sub">
                      <span className="over">{imp.overcharged} overcharged</span> · <span className="under">{imp.undercharged} undercharged</span>
                    </span>
                  )}
                </div>
                <div className="card kpi">
                  <span className="kpi-label">GST misreported</span>
                  <span className="kpi-value">{imp && !s.running ? rsWhole(imp.projected_monthly_tax * s.scale) : "–"}</span>
                  <span className="kpi-sub">
                    per month, projected{imp && !s.running && <> · {rs(imp.tax_misreported)} in sample</>}
                  </span>
                </div>
                <label className="volume">
                  Projected at
                  <input
                    type="number"
                    min={1}
                    step={1000}
                    value={s.volume}
                    onChange={(e) => s.setVolume(Math.max(1, Number(e.target.value) || 1))}
                  />
                  invoices a month ({num(s.volume)}). Projections scale the {sum?.total ?? 60}-scenario sample; they are not
                  measurements.
                </label>
              </div>
            </section>

            <section className="card">
              <div className="section-head">
                <h2>Scenarios</h2>
                <span className="legend">
                  <i className="cell cell-ok" /> identical <i className="cell cell-bad" /> differs <i className="cell cell-bad cell-new" /> new
                </span>
              </div>
              <ResultGrid results={s.results} total={s.total} onOpen={(id) => setModal({ id })} />
            </section>

            <section>
              <div className="section-head">
                <h2>
                  Findings{!s.running && s.active.length > 0 && <span className="count">{s.active.length}</span>}
                </h2>
                {s.explaining > 0 && <span className="muted">Tracing {s.explaining} group(s) to the code…</span>}
              </div>
              {!s.running && s.done > 0 && s.active.length === 0 && (
                <p className="alert alert-good">No mismatches. billing-v2 returned exactly what billing-v1 returned in every scenario.</p>
              )}
              <div className="findings">
                {s.active.map((g) => (
                  <FindingCard key={g.key} group={g} results={s.byId} scale={s.scale} onOpen={(id) => setModal({ id })} />
                ))}
              </div>
              {s.fixed.length > 0 && (
                <details className="fixed-list">
                  <summary>{s.fixed.reduce((n, g) => n + g.scenario_ids.length, 0)} scenarios fixed since the previous run</summary>
                  <div className="findings">
                    {s.fixed.map((g) => (
                      <FindingCard key={g.key} group={g} results={s.byId} scale={s.scale} onOpen={(id) => setModal({ id })} />
                    ))}
                  </div>
                </details>
              )}
            </section>
          </>
        )}

        {s.loaded && (
          <section className="card tools">
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === "try"} className={tab === "try" ? "on" : ""} onClick={() => setTab("try")}>
                Try a scenario
              </button>
              {s.me?.is_admin && (
                <button role="tab" aria-selected={tab === "break"} className={tab === "break" ? "on" : ""} onClick={() => setTab("break")}>
                  Break it live
                </button>
              )}
            </div>
            {tab === "try" || !s.me?.is_admin ? (
              <TryScenario onOpen={(r) => setModal({ result: r })} />
            ) : (
              <BreakItPanel onChanged={s.markStale} />
            )}
          </section>
        )}
      </main>

      {modal && <DiffModal id={modal.id} preloaded={modal.result} onClose={() => setModal(null)} />}
    </div>
  );
}
