import { loc, rs, rsWhole, show, signed } from "../format";
import type { Group, ResultSummary } from "../types";

interface Props {
  group: Group;
  results: Map<string, ResultSummary>;
  onOpen: (id: string) => void;
  big?: boolean;
}

const STATUS_LABEL = { NEW: "New since last run", UNCHANGED: "Known mismatch", FIXED: "Fixed" } as const;

export function MismatchCard({ group, results, onOpen, big }: Props) {
  const e = group.explanation;
  const imp = group.impact;
  const example = results.get(group.scenario_ids[0]);
  // Several steps return the same invoice; show each field once, from the latest step.
  const latest = new Map<string, NonNullable<typeof example>["diffs"][number]>();
  for (const d of example?.diffs ?? []) latest.set(d.field, d);
  const keyDiffs = [...latest.values()].slice(0, 5);
  const label = group.first_run
    ? "Mismatch found"
    : group.status === "NEW" && group.origin === "changed"
      ? "Changed since last run"
      : STATUS_LABEL[group.status];
  const tone = group.first_run ? "found" : group.status.toLowerCase();

  return (
    <article className={`card card-${tone} ${big ? "card-big" : ""}`}>
      <header className="card-head">
        <span className={`badge badge-${tone}`}>{label}</span>
        <h3>{e?.cause ?? `Difference in ${group.fields.join(", ")}`}</h3>
      </header>

      {e?.explanation && <p className="card-why">{e.explanation}</p>}

      {e?.recent_change && e.changed_line && (
        <div className="changed-line">
          <span className="changed-label">Changed since last run</span>
          <code>{e.changed_line}</code>
        </div>
      )}

      {imp && (
        <dl className="impact">
          <div>
            <dt>Invoices</dt>
            <dd>{imp.invoices_affected}</dd>
          </div>
          <div>
            <dt>Mis-billed</dt>
            <dd>{rs(imp.rupees_wrong)}</dd>
          </div>
          <div>
            <dt>Over / under</dt>
            <dd>
              <span className="over">{imp.overcharged} over</span> · <span className="under">{imp.undercharged} under</span>
            </dd>
          </div>
          <div>
            <dt>GST misreported</dt>
            <dd>{rs(imp.tax_misreported)}</dd>
          </div>
          <div className="impact-projection">
            <dt>Projected / month</dt>
            <dd>
              {rsWhole(imp.projected_monthly_rupees)} billed · {rsWhole(imp.projected_monthly_tax)} GST
              <small> (projection from sample)</small>
            </dd>
          </div>
        </dl>
      )}

      {group.status !== "FIXED" && example && (
        <div className="example">
          <div className="example-head">
            <span>
              Example {example.id}: {example.summary}
            </span>
            <button className="link" onClick={() => onOpen(example.id)}>
              Side-by-side diff
            </button>
          </div>
          <table className="vs">
            <thead>
              <tr>
                <th>Field</th>
                <th>v1 (legacy)</th>
                <th>v2 (rewrite)</th>
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              {keyDiffs.map((d) => (
                <tr key={d.path}>
                  <td>{d.path.split(".").slice(1).join(".") || d.path}</td>
                  <td>{show(d.v1)}</td>
                  <td>{show(d.v2)}</td>
                  <td className={d.delta && d.delta > 0 ? "over" : d.delta && d.delta < 0 ? "under" : ""}>
                    {d.delta !== null ? signed(d.delta) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {e && (e.v1_file || e.v2_file) && (
        <footer className="code-refs">
          <span>
            v1 <code>{loc(e.v1_file, e.v1_line)}</code>
          </span>
          <span>
            v2 <code>{loc(e.v2_file, e.v2_line)}</code>
          </span>
          {e.suggested_fix && group.status !== "FIXED" && <span className="fix">Suggested fix (human applies): {e.suggested_fix}</span>}
        </footer>
      )}

      <div className="card-ids">
        {group.scenario_ids.map((id) => (
          <button key={id} className="chip" onClick={() => onOpen(id)}>
            {id}
          </button>
        ))}
      </div>
    </article>
  );
}
