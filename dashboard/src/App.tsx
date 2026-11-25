import { useCallback, useEffect, useMemo, useState } from "react";
import { agentHealth, getLatestRun, reportUrl, streamRun, type AdhocResponse } from "./api";
import { BreakItPanel } from "./components/BreakItPanel";
import { DiffModal } from "./components/DiffModal";
import { Gauge } from "./components/Gauge";
import { JudgeBox } from "./components/JudgeBox";
import { MismatchCard } from "./components/MismatchCard";
import { ResultGrid } from "./components/ResultGrid";
import { num, rs, rsWhole } from "./format";
import type { FullResult, Group, ResultSummary, Run } from "./types";

const STORY = ["Headline", "Parity", "Mismatches", "Break it", "Re-run", "Report"] as const;

function readVolume(): number {
  try {
    return Number(localStorage.getItem("doppel.volume")) || 100_000;
  } catch {
    return 100_000;
  }
}

export default function App() {
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [total, setTotal] = useState(0);
  const [identical, setIdentical] = useState(0);
  const [running, setRunning] = useState(false);
  const [explaining, setExplaining] = useState(0);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("");
  const [volume, setVolume] = useState(readVolume);
  const [modal, setModal] = useState<{ id?: string; result?: FullResult } | null>(null);
  const [story, setStory] = useState(() => new URLSearchParams(location.search).has("story"));
  const [scene, setScene] = useState(0);
  const [dirty, setDirty] = useState(false);

  const load = useCallback((r: Run) => {
    setRun(r);
    setResults(r.results);
    setGroups(r.groups);
    setTotal(r.summary.total);
    setIdentical(r.summary.identical);
  }, []);

  useEffect(() => {
    getLatestRun().then((r) => r && load(r)).catch(() => undefined);
    agentHealth().then((h) => setMode(h.mode)).catch(() => setError("Doppel agent is not reachable on :8000"));
  }, [load]);

  useEffect(() => {
    try {
      localStorage.setItem("doppel.volume", String(volume));
    } catch {
      /* per-viewer convenience only */
    }
  }, [volume]);

  const start = useCallback(
    async (fresh = false) => {
      setRunning(true);
      setError("");
      setResults([]);
      setGroups([]);
      setIdentical(0);
      setExplaining(0);
      try {
        await streamRun(volume, fresh, (e) => {
          if (e.type === "start") setTotal(e.total);
          else if (e.type === "result") {
            setResults((rs) => [...rs, e.result]);
            setIdentical(e.identical);
          } else if (e.type === "explaining") setExplaining(e.groups);
          else if (e.type === "group") setGroups((gs) => [...gs, e.group]);
          else if (e.type === "done") {
            load(e.run);
            setDirty(false);
          } else if (e.type === "error") setError(e.detail);
        });
      } catch (err) {
        setError(String((err as Error).message ?? err));
      } finally {
        setRunning(false);
        setExplaining(0);
      }
    },
    [volume, load],
  );

  const byId = useMemo(() => new Map(results.map((r) => [r.id, r])), [results]);
  const open = (id: string) => setModal({ id });
  const openAdhoc = (r: AdhocResponse["result"]) => setModal({ result: r });
  const active = groups.filter((g) => g.status !== "FIXED");
  const fixed = groups.filter((g) => g.status === "FIXED");
  const s = run?.summary;
  const imp = s?.impact;
  const done = results.length;

  // Re-scale the projection on the client when the volume input changes (same formula as the agent).
  const scale = s ? volume / s.monthly_volume : 1;
  const headline =
    s && !running
      ? imp && s.identical < s.total
        ? `If you switched today: ${Math.round(100 - s.parity_pct)}% of bills wrong, ~${rsWhole(imp.projected_monthly_rupees * scale)}/month mis-billed and ~${rsWhole(imp.projected_monthly_tax * scale)}/month GST misreported (projected).`
        : "If you switched today: every bill in the sample matches the legacy system."
      : running
        ? "Checking both systems…"
        : "Run a parity check to see what switching would cost.";

  useEffect(() => {
    if (!story) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, select")) return;
      if (e.key === "ArrowRight" || e.key === " ") setScene((n) => Math.min(STORY.length - 1, n + 1));
      if (e.key === "ArrowLeft") setScene((n) => Math.max(0, n - 1));
      if (e.key === "Escape") setStory(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [story]);

  const gauge = (
    <Gauge identical={identical} done={done} total={total} running={running} previousPct={run?.previous_summary?.parity_pct} />
  );
  const runButtons = (
    <div className="row run-buttons">
      <button className="btn btn-primary btn-lg" onClick={() => start(false)} disabled={running}>
        {running ? (explaining ? `Explaining ${explaining} group(s)…` : `Running ${done}/${total || "…"}`) : run ? "Re-run" : "Doppel, are these two the same?"}
      </button>
      <button className="btn" onClick={() => start(true)} disabled={running} title="Start over: call billing-v1 again and forget previous runs">
        Fresh start
      </button>
      <a className={`btn ${run ? "" : "btn-disabled"}`} href={run ? reportUrl() : undefined}>
        Export report (.md)
      </a>
    </div>
  );
  const impactBar = imp && s && s.identical < s.total && (
    <section className="impact-bar">
      <div>
        <span className="big-num">{imp.invoices_affected}</span> of {s.total} sample bills wrong
      </div>
      <div>
        <span className="big-num">{rs(imp.rupees_wrong)}</span> mis-billed: <span className="over">{imp.overcharged} overcharged</span>,{" "}
        <span className="under">{imp.undercharged} undercharged</span>
      </div>
      <div>
        <span className="big-num">{rs(imp.tax_misreported)}</span> GST misreported
      </div>
      <div className="projection">
        Projection at{" "}
        <input type="number" min={1000} step={1000} value={volume} onChange={(e) => setVolume(Math.max(1, Number(e.target.value) || 1))} />{" "}
        invoices/month ({num(volume)}): <strong>{rsWhole(imp.projected_monthly_rupees * scale)}</strong> mis-billed,{" "}
        <strong>{rsWhole(imp.projected_monthly_tax * scale)}</strong> GST misreported per month.{" "}
        <em>Projection from the {s.total}-scenario sample, not a measurement.</em>
      </div>
    </section>
  );
  const cards = (big = false) => (
    <div className={`cards ${big ? "cards-big" : ""}`}>
      {!running && done > 0 && active.length === 0 && <p className="all-good">No mismatches. billing-v2 behaves exactly like billing-v1.</p>}
      {active.map((g) => (
        <MismatchCard key={g.key} group={g} results={byId} onOpen={open} big={big} />
      ))}
      {fixed.length > 0 && (
        <details className="fixed" open={big}>
          <summary>{fixed.reduce((n, g) => n + g.scenario_ids.length, 0)} scenario(s) fixed since the previous run</summary>
          {fixed.map((g) => (
            <MismatchCard key={g.key} group={g} results={byId} onOpen={open} big={big} />
          ))}
        </details>
      )}
    </div>
  );
  const countsLine = run && !running && (
    <p className="counts">
      vs previous run: <span className="badge badge-new">{run.counts.NEW} new</span>{" "}
      <span className="badge badge-fixed">{run.counts.FIXED} fixed</span>{" "}
      <span className="badge badge-unchanged">{run.counts.UNCHANGED} unchanged</span> · {run.duration_s}s · billing-v2 at{" "}
      <code>{run.v2_commit.slice(0, 8)}</code>
    </p>
  );

  if (story) {
    const name = STORY[scene];
    return (
      <div className="story">
        <nav className="story-nav">
          {STORY.map((label, i) => (
            <button key={label} className={`story-step ${i === scene ? "on" : ""}`} onClick={() => setScene(i)}>
              {i + 1}. {label}
            </button>
          ))}
          <button className="btn" onClick={() => setStory(false)}>
            Exit story
          </button>
        </nav>
        <main className="story-scene">
          {name === "Headline" && (
            <div className="story-center">
              <p className="kicker">AI rewrote this billing system in a weekend.</p>
              <h1 className="story-headline">{headline}</h1>
            </div>
          )}
          {name === "Parity" && (
            <div className="story-center">
              {gauge}
              {runButtons}
            </div>
          )}
          {name === "Mismatches" && cards(true)}
          {name === "Break it" && <BreakItPanel big onChanged={() => setDirty(true)} />}
          {name === "Re-run" && (
            <div className="story-center">
              {gauge}
              {runButtons}
              {countsLine}
              {dirty && <p className="kicker">billing-v2 changed. Re-run to see what Doppel catches.</p>}
              {cards(true)}
            </div>
          )}
          {name === "Report" && (
            <div className="story-center">
              <h1 className="story-headline">{headline}</h1>
              {impactBar}
              <a className="btn btn-primary btn-lg" href={run ? reportUrl() : undefined}>
                Download the signed-off parity report
              </a>
              <p className="kicker">Doppel proves the new system is still your system before you bet the business on it.</p>
            </div>
          )}
        </main>
        <footer className="story-foot">
          <button className="btn" disabled={scene === 0} onClick={() => setScene(scene - 1)}>
            ← Back
          </button>
          <span>
            {scene + 1} / {STORY.length} · arrow keys to move
          </span>
          <button className="btn btn-primary" disabled={scene === STORY.length - 1} onClick={() => setScene(scene + 1)}>
            Next →
          </button>
        </footer>
        {modal && <DiffModal id={modal.id} preloaded={modal.result} onClose={() => setModal(null)} />}
      </div>
    );
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo" aria-hidden>
            <i />
            <i />
          </span>
          <div>
            <h1>Doppel</h1>
            <p>Is the AI rewrite still your system? billing_v1 (Python) vs billing_v2 (TypeScript), both through Synapse MCP.</p>
          </div>
        </div>
        <div className="top-right">
          {mode && <span className={`badge ${mode === "mcp" ? "badge-ok" : "badge-unchanged"}`}>{mode === "mcp" ? "via Synapse MCP" : "direct HTTP (dev)"}</span>}
          <button className="btn" onClick={() => { setStory(true); setScene(0); }}>
            Story mode
          </button>
        </div>
      </header>

      <p className="headline">{headline}</p>
      {error && <p className="error">{error}</p>}

      <section className="hero">
        <div className="hero-left">
          {gauge}
          {runButtons}
          {countsLine}
        </div>
        <div className="hero-right">
          <h2>Scenarios</h2>
          <ResultGrid results={results} total={total} onOpen={open} />
          <p className="legend">
            <span className="cell cell-ok" /> identical <span className="cell cell-bad" /> differs <span className="cell cell-bad cell-new" /> new since last run
          </p>
        </div>
      </section>

      {impactBar}

      <section>
        <h2>Mismatches{explaining ? ` · explaining ${explaining} group(s) from the code…` : ""}</h2>
        {cards()}
      </section>

      <div className="two-col">
        <JudgeBox onOpenResult={openAdhoc} />
        <BreakItPanel onChanged={() => setDirty(true)} />
      </div>
      {dirty && !running && <p className="sticky-hint">billing-v2 changed. Press Re-run.</p>}

      {modal && <DiffModal id={modal.id} preloaded={modal.result} onClose={() => setModal(null)} />}
    </div>
  );
}
