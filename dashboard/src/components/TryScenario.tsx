import { useState, type FormEvent } from "react";
import { runAdhoc, type AdhocResponse } from "../lib/api";
import { loc, show, signed } from "../lib/format";

const EXAMPLES = [
  "Kerala customer, 10% coupon, returns 1 of 3 items",
  "Delhi customer pays a ₹2,999 order 5 days late; it was due on a Sunday",
  "Maharashtra customer buys three USB-C cables and a phone charger",
];

export function TryScenario({ onOpen }: { onOpen: (r: AdhocResponse["result"]) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [out, setOut] = useState<AdhocResponse | null>(null);

  const go = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    setOut(null);
    try {
      setOut(await runAdhoc(text.trim()));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const r = out?.result;
  const e = out?.explanation;
  return (
    <div className="tool">
      <p className="muted">Describe a billing case in plain English. Doppel plans the API calls and runs them on both systems.</p>
      <form className="row" onSubmit={go}>
        <input
          aria-label="Scenario"
          placeholder={EXAMPLES[0]}
          value={text}
          onChange={(ev) => setText(ev.target.value)}
          disabled={busy}
        />
        <button className="btn btn-primary" disabled={busy || !text.trim()}>
          {busy ? "Running…" : "Run on both"}
        </button>
      </form>
      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" onClick={() => setText(ex)} disabled={busy}>
            {ex}
          </button>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}
      {out && r && (
        <div className={`result ${r.match ? "result-ok" : "result-bad"}`}>
          <p className="result-title">
            <strong>{r.match ? "Identical on both systems" : `${r.diffs.length} field${r.diffs.length > 1 ? "s" : ""} differ`}</strong>
            <span className="muted"> · {out.plan.summary}</span>
          </p>
          <p className="muted small">
            {r.steps.map((s) => s.tool).join(" → ")}
            {out.plan.assumptions && <> · Assumed: {out.plan.assumptions}</>} ·{" "}
            <button className="link" onClick={() => onOpen(r)}>
              Side-by-side
            </button>
          </p>
          {!r.match && (
            <ul className="diff-list">
              {r.diffs.slice(0, 5).map((d) => (
                <li key={d.path}>
                  <code>{d.field}</code> v1 {show(d.v1)} · v2 {show(d.v2)}
                  {d.delta !== null && <strong> ({signed(d.delta)})</strong>}
                </li>
              ))}
            </ul>
          )}
          {e && e.source !== "fallback" && (
            <p>
              <strong>{e.cause}.</strong> {e.explanation} <code>{loc(e.v2_file, e.v2_line)}</code>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
