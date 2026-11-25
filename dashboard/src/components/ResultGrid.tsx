import type { ResultSummary } from "../types";

interface Props {
  results: ResultSummary[];
  total: number;
  onOpen: (id: string) => void;
}

/** One square per scenario, filled in as results stream. */
export function ResultGrid({ results, total, onOpen }: Props) {
  const cells = Array.from({ length: Math.max(total, results.length) }, (_, i) => results[i]);
  return (
    <div className="grid" role="list">
      {cells.map((r, i) =>
        r ? (
          <button
            key={r.id}
            role="listitem"
            className={`cell ${r.match ? "cell-ok" : "cell-bad"} ${r.status === "NEW" ? "cell-new" : ""} ${r.status === "FIXED" ? "cell-fixed" : ""}`}
            title={`${r.id} ${r.summary}${r.match ? " — identical" : " — differs"} (${r.status})`}
            onClick={() => onOpen(r.id)}
          >
            {r.id.slice(1)}
          </button>
        ) : (
          <span key={i} className="cell cell-pending" />
        ),
      )}
    </div>
  );
}
