interface Props {
  identical: number;
  done: number;
  total: number;
  previousPct?: number | null;
  running: boolean;
}

/** Half-circle parity gauge. Fills as results stream in; the number is identical / total so far. */
export function Gauge({ identical, done, total, previousPct, running }: Props) {
  const pct = done ? (100 * identical) / done : 0;
  const progress = total ? done / total : 0;
  const r = 90;
  const arc = Math.PI * r;
  const filled = arc * (pct / 100) * progress;
  const tone = pct >= 99.95 ? "good" : pct >= 90 ? "warn" : "bad";
  const delta = previousPct != null && !running && done === total ? Math.round(pct) - Math.round(previousPct) : null;

  return (
    <div className={`gauge gauge-${tone}`} aria-label={`Parity ${Math.round(pct)} percent`}>
      <svg viewBox="0 0 220 125" role="img">
        <path d="M20 110 A90 90 0 0 1 200 110" className="gauge-track" />
        <path
          d="M20 110 A90 90 0 0 1 200 110"
          className="gauge-fill"
          strokeDasharray={`${filled} ${arc}`}
        />
      </svg>
      <div className="gauge-value">{done ? `${Math.round(pct)}%` : "—"}</div>
      <div className="gauge-caption">
        {done ? `${identical}/${done} identical` : "No run yet"}
        {running && total ? ` · running ${done}/${total}` : ""}
      </div>
      {delta != null && delta !== 0 && (
        <div className={`gauge-delta ${delta > 0 ? "up" : "down"}`}>
          {delta > 0 ? "▲" : "▼"} {Math.abs(delta)} pts vs previous run ({Math.round(previousPct!)}%)
        </div>
      )}
    </div>
  );
}
