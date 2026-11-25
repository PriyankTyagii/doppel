import { loc, rs, rsWhole, show, signed } from "../lib/format";
import type { FieldDiff, Group, ResultSummary } from "../types";

interface Props {
  group: Group;
  results: Map<string, ResultSummary>;
  scale: number;
  onOpen: (id: string) => void;
  large?: boolean;
}

function statusOf(g: Group): { label: string; tone: string } {
  if (g.status === "FIXED") return { label: "Fixed", tone: "good" };
  if (g.first_run) return { label: "Mismatch", tone: "bad" };
  if (g.status === "NEW") return { label: g.origin === "changed" ? "Changed since last run" : "New since last run", tone: "new" };
  return { label: "Known", tone: "muted" };
}

export function FindingCard({ group, results, scale, onOpen, large }: Props) {
  const e = group.explanation;
  const imp = group.impact;
  const status = statusOf(group);
  const example = results.get(group.scenario_ids[0]);
  // Several steps return the same invoice; show each field once, from the latest step.
  const fields = new Map<string, FieldDiff>();
  for (const d of example?.diffs ?? []) fields.set(d.field, d);
  const rows = [...fields.values()].slice(0, 6);
  const explained = e && e.source !== "fallback";

  return (
    <article className={`finding finding-${status.tone} ${large ? "finding-large" : ""}`}>
      <div className="finding-head">
        <span className={`pill pill-${status.tone}`}>{status.label}</span>
        <h3>{explained ? e.cause : `Difference in ${group.fields.join(", ")}`}</h3>
      </div>

      {e?.explanation && <p className="finding-why">{e.explanation}</p>}

      {e?.recent_change && e.changed_line && (
        <p className="changed">
          <span>Changed line</span>
          <code>{e.changed_line}</code>
        </p>
      )}

      {imp && (
        <dl className="finding-stats">
          <div>
            <dt>Invoices</dt>
            <dd>{imp.invoices_affected}</dd>
          </div>
          <div>
            <dt>Mis-billed</dt>
            <dd>{rs(imp.rupees_wrong)}</dd>
            {(imp.overcharged > 0 || imp.undercharged > 0) && (
              <dd className="sub">
                {imp.overcharged > 0 && <span className="over">{imp.overcharged} overcharged</span>}
                {imp.overcharged > 0 && imp.undercharged > 0 && " · "}
                {imp.undercharged > 0 && <span className="under">{imp.undercharged} undercharged</span>}
              </dd>
            )}
          </div>
          <div>
            <dt>GST misreported</dt>
            <dd>{rs(imp.tax_misreported)}</dd>
          </div>
          {group.status !== "FIXED" && (
            <div>
              <dt>Projected per month</dt>
              <dd>{rsWhole((imp.projected_monthly_rupees + imp.projected_monthly_tax) * scale)}</dd>
              <dd className="sub">billing + GST, projection</dd>
            </div>
          )}
        </dl>
      )}

      {group.status !== "FIXED" && (
        <details className="evidence" open={large}>
          <summary>Evidence and code</summary>
          {example && (
            <>
              <div className="evidence-head">
                <span>
                  {example.id} · {example.summary}
                </span>
                <button className="link" onClick={() => onOpen(example.id)}>
                  Full side-by-side
                </button>
              </div>
              <table className="vs">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>v1 legacy</th>
                    <th>v2 rewrite</th>
                    <th className="num">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((d) => (
                    <tr key={d.path}>
                      <td>{d.field}</td>
                      <td>{show(d.v1)}</td>
                      <td>{show(d.v2)}</td>
                      <td className={`num ${d.delta && d.delta > 0 ? "over" : d.delta && d.delta < 0 ? "under" : ""}`}>
                        {d.delta !== null ? signed(d.delta) : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {explained && (
            <dl className="code-refs">
              <div>
                <dt>Reference (v1)</dt>
                <dd>
                  <code>{loc(e.v1_file, e.v1_line)}</code>
                </dd>
              </div>
              <div>
                <dt>Rewrite (v2)</dt>
                <dd>
                  <code>{loc(e.v2_file, e.v2_line)}</code>
                </dd>
              </div>
              {e.suggested_fix && (
                <div className="wide">
                  <dt>Suggested fix, for a human to apply</dt>
                  <dd>{e.suggested_fix}</dd>
                </div>
              )}
            </dl>
          )}
          <div className="chips">
            {group.scenario_ids.map((id) => (
              <button key={id} className="chip" onClick={() => onOpen(id)}>
                {id}
              </button>
            ))}
          </div>
        </details>
      )}
    </article>
  );
}
