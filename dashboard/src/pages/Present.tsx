import { useEffect, useState } from "react";
import { BreakItPanel } from "../components/BreakItPanel";
import { DiffModal } from "../components/DiffModal";
import { FindingCard } from "../components/FindingCard";
import { Gauge } from "../components/Gauge";
import { downloadReport } from "../lib/api";
import { Link } from "../lib/router";
import { useRun } from "../lib/useRun";
import { verdict } from "./Dashboard";

const SCENES = ["Headline", "Parity", "Findings", "Break it", "Re-run", "Report"] as const;

/** Presentation mode: one idea per screen, large type, arrow keys to move. */
export function Present() {
  const s = useRun();
  const [scene, setScene] = useState(0);
  const [modal, setModal] = useState<string | null>(null);
  const scenes = SCENES.filter((n) => n !== "Break it" || s.me?.is_admin);
  const name = scenes[Math.min(scene, scenes.length - 1)];
  const v = verdict(s);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, select") || modal) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") setScene((n) => Math.min(scenes.length - 1, n + 1));
      if (e.key === "ArrowLeft" || e.key === "PageUp") setScene((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [scenes.length, modal]);

  const gauge = (
    <Gauge identical={s.identical} done={s.done} total={s.total} running={s.running} previousPct={s.run?.previous_summary?.parity_pct} />
  );
  const runButton = (
    <button className="btn btn-primary btn-xl" onClick={() => s.start(false)} disabled={s.running || !s.loaded}>
      {s.running ? (s.explaining ? "Explaining…" : `Running ${s.done}/${s.total || "…"}`) : "Run parity check"}
    </button>
  );
  const findings = (
    <div className="findings">
      {s.active.map((g) => (
        <FindingCard key={g.key} group={g} results={s.byId} scale={s.scale} onOpen={setModal} large />
      ))}
    </div>
  );

  return (
    <div className="present">
      <nav className="present-nav">
        {scenes.map((n, i) => (
          <button key={n} className={i === scene ? "on" : ""} onClick={() => setScene(i)}>
            {n}
          </button>
        ))}
        <Link href="/app" className="btn btn-sm btn-ghost present-exit">
          Exit
        </Link>
      </nav>

      <main className="present-stage">
        {s.error && <p className="alert alert-bad">{s.error}</p>}
        {name === "Headline" && (
          <div className="stage-center">
            <p className="kicker">AI rewrote this billing system in a weekend.</p>
            <h1 className="stage-title">{v.text}</h1>
          </div>
        )}
        {name === "Parity" && (
          <div className="stage-center">
            {gauge}
            {runButton}
          </div>
        )}
        {name === "Findings" && findings}
        {name === "Break it" && <BreakItPanel onChanged={s.markStale} large />}
        {name === "Re-run" && (
          <div className="stage-center">
            {s.stale && !s.running && <p className="kicker">billing-v2 just changed.</p>}
            {gauge}
            {runButton}
            {findings}
          </div>
        )}
        {name === "Report" && (
          <div className="stage-center">
            <h1 className="stage-title">{v.text}</h1>
            <button className="btn btn-primary btn-xl" onClick={() => downloadReport().catch(() => undefined)} disabled={!s.run}>
              Download the parity report
            </button>
            <p className="kicker">Doppel proves the new system is still your system before you bet the business on it.</p>
          </div>
        )}
      </main>

      <footer className="present-foot">
        <button className="btn btn-ghost" disabled={scene === 0} onClick={() => setScene(scene - 1)}>
          Back
        </button>
        <span className="muted">
          {scene + 1} / {scenes.length} · arrow keys
        </span>
        <button className="btn btn-primary" disabled={scene === scenes.length - 1} onClick={() => setScene(scene + 1)}>
          Next
        </button>
      </footer>
      {modal && <DiffModal id={modal} onClose={() => setModal(null)} />}
    </div>
  );
}
