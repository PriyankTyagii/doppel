import { useState } from "react";
import { runAdhoc, type AdhocResponse } from "../api";
import { loc, show, signed } from "../format";

interface Props {
  onOpenResult: (r: AdhocResponse["result"]) => void;
}

export function JudgeBox({ onOpenResult }: Props) {
  const [text, setText] = useState("Kerala customer, 10% coupon, returns 1 of 3 items");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [out, setOut] = useState<AdhocResponse | null>(null);

  const go = async () => {
    setBusy(true);
    setError("");
    setOut(null);
    try {
      setOut(await runAdhoc(text));
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const r = out?.result;
  const e = out?.explanation;
  return (
    <section className="panel">
      <h2>Judge's scenario</h2>
      <p className="muted">Describe any billing case in plain English. Doppel plans the tool calls and runs them on both systems.</p>
      <div className="row">
        <input value={text} onChange={(ev) => setText(ev.target.value)} onKeyDown={(ev) => ev.key === "Enter" && !busy && go()} />
        <button className="btn btn-primary" onClick={go} disabled={busy || !text.trim()}>
          {busy ? "Running on both…" : "Run on both"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {out && r && (
        <div className={`adhoc ${r.match ? "adhoc-ok" : "adhoc-bad"}`}>
          <p>
            <strong>{out.plan.summary}</strong> — {r.match ? "identical on both systems" : `${r.diffs.length} field(s) differ`}
          </p>
          {out.plan.assumptions && <p className="muted">Assumed: {out.plan.assumptions}</p>}
          <p className="muted">
            Steps: {r.steps.map((s) => s.tool).join(" → ")}{" "}
            <button className="link" onClick={() => onOpenResult(r)}>
              Side-by-side diff
            </button>
          </p>
          {!r.match && (
            <ul className="diff-list">
              {r.diffs.slice(0, 5).map((d) => (
                <li key={d.path}>
                  <code>{d.path}</code>: v1 {show(d.v1)} · v2 {show(d.v2)} {d.delta !== null && <strong>({signed(d.delta)})</strong>}
                </li>
              ))}
            </ul>
          )}
          {e && (
            <p>
              <strong>{e.cause}.</strong> {e.explanation}{" "}
              {e.v2_file && (
                <code>
                  {loc(e.v1_file, e.v1_line)} vs {loc(e.v2_file, e.v2_line)}
                </code>
              )}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
