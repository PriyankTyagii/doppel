import { useEffect, useState } from "react";
import { getScenario } from "../lib/api";
import type { FullResult } from "../types";

interface Props {
  id?: string;
  preloaded?: FullResult;
  onClose: () => void;
}

const IGNORED = new Set(["id", "customer_id", "invoice_id", "created_at"]);

/** Renders one value as indented JSON lines, marking lines whose path differs. */
function lines(value: unknown, diffPaths: Set<string>, path = "", indent = 0, key?: string): { text: string; bad: boolean; muted: boolean }[] {
  const pad = "  ".repeat(indent);
  const label = key !== undefined ? `"${key}": ` : "";
  const muted = key !== undefined && IGNORED.has(key);
  if (value && typeof value === "object") {
    const isArr = Array.isArray(value);
    const entries = isArr ? (value as unknown[]).map((v, i) => [String(i), v] as const) : Object.entries(value as object);
    const out = [{ text: `${pad}${label}${isArr ? "[" : "{"}`, bad: false, muted }];
    for (const [k, v] of entries) {
      const p = isArr ? `${path}[${k}]` : path ? `${path}.${k}` : k;
      out.push(...lines(v, diffPaths, p, indent + 1, isArr ? undefined : k));
    }
    out.push({ text: `${pad}${isArr ? "]" : "}"}`, bad: false, muted });
    return out;
  }
  return [{ text: `${pad}${label}${JSON.stringify(value)}`, bad: diffPaths.has(path), muted }];
}

export function DiffModal({ id, preloaded, onClose }: Props) {
  const [data, setData] = useState<FullResult | null>(preloaded ?? null);
  const [error, setError] = useState("");
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (preloaded || !id) return;
    getScenario(id).then(setData).catch((e) => setError(String(e.message ?? e)));
  }, [id, preloaded]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const steps = data?.steps ?? [];
  const prefix = steps[step] ? `${step + 1}:${steps[step].tool}` : "";
  const diffPaths = new Set(
    (data?.diffs ?? []).filter((d) => d.path.startsWith(prefix + ".") || d.path === prefix).map((d) => d.path.slice(prefix.length + 1)),
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className="modal-head">
          <h2>
            {data ? `${data.id}: ${data.summary}` : id}
            {data && <span className={`pill ${data.match ? "pill-good" : "pill-bad"}`}>{data.match ? "identical" : "differs"}</span>}
          </h2>
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </header>
        {error && <p className="form-error">{error}</p>}
        {data && (
          <>
            <div className="steps">
              {steps.map((s, i) => {
                const p = `${i + 1}:${s.tool}`;
                const bad = data.diffs.some((d) => d.path === p || d.path.startsWith(p + "."));
                return (
                  <button key={i} className={`chip ${i === step ? "chip-on" : ""} ${bad ? "chip-bad" : ""}`} onClick={() => setStep(i)}>
                    {i + 1}. {s.tool}
                  </button>
                );
              })}
            </div>
            <pre className="args">{JSON.stringify(steps[step]?.args ?? {}, null, 1)}</pre>
            <div className="sbs">
              {(["v1", "v2"] as const).map((sys) => (
                <div key={sys} className="sbs-col">
                  <h4>{sys === "v1" ? "billing_v1 (Python, legacy)" : "billing_v2 (TypeScript, rewrite)"}</h4>
                  <pre>
                    {lines(data[sys][step], diffPaths).map((l, i) => (
                      <div key={i} className={l.bad ? "line-bad" : l.muted ? "line-muted" : ""}>
                        {l.text}
                      </div>
                    ))}
                  </pre>
                </div>
              ))}
            </div>
            <p className="note">Greyed fields (ids, timestamps) are ignored by the comparator.</p>
            {data.trace?.length ? (
              <details className="trace">
                <summary>Tool calls ({data.trace.length})</summary>
                <ol>
                  {data.trace.map((t, i) => (
                    <li key={i}>
                      <span className={`tag tag-${t.system === "billing_v1" ? "v1" : "v2"}`}>{t.system === "billing_v1" ? "v1" : "v2"}</span>{" "}
                      <code>
                        {t.tool}({JSON.stringify(t.args)})
                      </code>
                    </li>
                  ))}
                </ol>
              </details>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
