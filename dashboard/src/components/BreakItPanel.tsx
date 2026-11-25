import { useCallback, useEffect, useState } from "react";
import {
  applyEdit,
  applyMutation,
  checkEdit,
  controlState,
  getDefinition,
  listDefinitions,
  listMutations,
  restoreDemo,
} from "../lib/api";
import type { ControlState, Definition, Mutation } from "../types";

interface Props {
  onChanged: () => void;
  large?: boolean;
}

interface Outcome {
  ok: boolean;
  title: string;
  lines: string[];
}

function describe(res: Record<string, unknown>): string[] {
  const out: string[] = [];
  if (res.file) out.push(`Commit ${res.commit} on live-demo: ${res.file}:${res.line}`);
  if (res.healthy_after_s !== undefined) out.push(`billing-v2 restarted, healthy after ${res.healthy_after_s}s`);
  if (typeof res.rebuild === "string") out.push(res.rebuild);
  const syn = res.synapse as { ran?: boolean; detail?: string } | undefined;
  if (syn) out.push(syn.ran ? "synapse build --discover finished" : String(syn.detail));
  return out;
}

export function BreakItPanel({ onChanged, large }: Props) {
  const [state, setState] = useState<ControlState | null>(null);
  const [mutations, setMutations] = useState<Mutation[]>([]);
  const [defs, setDefs] = useState<Definition[]>([]);
  const [selected, setSelected] = useState("");
  const [original, setOriginal] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [offline, setOffline] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([controlState(), listMutations()]);
      setState(s);
      setMutations(m);
      setOffline("");
    } catch (e) {
      setOffline((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    listDefinitions().then(setDefs).catch(() => undefined);
  }, [refresh]);

  const act = async (label: string, fn: () => Promise<Record<string, unknown>>) => {
    setBusy(label);
    setOutcome(null);
    try {
      const res = await fn();
      if (res.applied === false) {
        setOutcome({ ok: false, title: "Type check failed, nothing applied", lines: [String(res.typecheck)] });
      } else {
        setOutcome({ ok: true, title: label, lines: describe(res) });
        onChanged();
      }
    } catch (e) {
      setOutcome({ ok: false, title: `${label} failed`, lines: [String((e as Error).message ?? e)] });
    } finally {
      setBusy("");
      refresh();
    }
  };

  const pick = async (key: string) => {
    setSelected(key);
    if (!key) return;
    const [file, name] = key.split("/");
    const d = await getDefinition(file, name);
    setOriginal(d.source ?? "");
    setSource(d.source ?? "");
  };

  const changedLines = source.split("\n").filter((l, i) => l !== original.split("\n")[i]).length;
  const [file, name] = selected.split("/");

  if (offline) {
    return (
      <div className={`tool ${large ? "tool-large" : ""}`}>
        <p className="form-error">{offline}</p>
      </div>
    );
  }

  return (
    <div className={`tool ${large ? "tool-large" : ""}`}>
      <div className="tool-head">
        <p className="muted">Each change is one committed, reversible edit to billing-v2, which then restarts. billing-v1 is never touched.</p>
        <div className="status-line">
          <span className={`dot ${state?.v2_healthy ? "dot-ok" : "dot-bad"}`} /> billing-v2 {state?.v2_healthy ? "healthy" : "down"} · branch{" "}
          <code>{state?.branch}</code>
          {state?.demo_active && <> · from <code>{state.pre_demo_commit}</code></>}
        </div>
      </div>

      <div className="mutations">
        {mutations.map((m) => (
          <button
            key={m.id}
            className={`mutation ${m.applied ? "mutation-on" : ""}`}
            disabled={!!busy || m.applied}
            onClick={() => act(m.title, () => applyMutation(m.id))}
            title={`${m.file}: ${m.find.trim()} → ${m.replace.trim()}`}
          >
            <strong>{m.title}</strong>
            <span>{m.description}</span>
            {m.applied && <em>applied</em>}
          </button>
        ))}
      </div>

      <details className="advanced">
        <summary>Advanced: edit one line by hand</summary>
        <div className="row">
          <select value={selected} onChange={(e) => pick(e.target.value)}>
            <option value="">Choose a function in billing-v2…</option>
            {defs.map((d) => (
              <option key={`${d.file}/${d.name}`} value={`${d.file}/${d.name}`}>
                {d.file} · {d.name} (lines {d.start}–{d.end})
              </option>
            ))}
          </select>
        </div>
        {selected && (
          <>
            <textarea
              className="code-edit"
              spellCheck={false}
              value={source}
              onChange={(e) => setSource(e.target.value)}
              rows={Math.min(18, source.split("\n").length + 1)}
            />
            <div className="row">
              <span className="muted">{changedLines === 1 ? "1 line changed" : `${changedLines} lines changed (exactly 1 allowed)`}</span>
              <button className="btn" disabled={!!busy || changedLines !== 1} onClick={() => act("Type check", async () => {
                const r = await checkEdit(file, name, source);
                return r.ok ? { rebuild: "Type check passed. Nothing applied yet." } : { applied: false, typecheck: r.typecheck };
              })}>
                Check
              </button>
              <button className="btn btn-danger" disabled={!!busy || changedLines !== 1} onClick={() => act(`Hand edit in ${name}()`, () => applyEdit(file, name, source))}>
                Type-check and apply
              </button>
            </div>
          </>
        )}
      </details>

      <div className="row">
        <button className="btn btn-restore" disabled={!!busy || !state?.demo_active} onClick={() => act("Restored billing-v2", restoreDemo)}>
          Restore billing-v2
        </button>
        {busy && <span className="muted">{busy}… restarting billing-v2</span>}
      </div>

      {outcome && (
        <div className={`outcome ${outcome.ok ? "outcome-ok" : "outcome-bad"}`}>
          <strong>{outcome.title}</strong>
          {outcome.lines.map((l, i) => (
            <pre key={i}>{l}</pre>
          ))}
          {outcome.ok && <p>Now press Re-run: billing-v1 results are cached, so only billing-v2 is called.</p>}
        </div>
      )}
    </div>
  );
}
