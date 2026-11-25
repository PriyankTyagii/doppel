import { useCallback, useEffect, useMemo, useState } from "react";
import { getLatestRun, getMe, streamRun } from "./api";
import type { Group, Me, ResultSummary, Run } from "../types";

const VOLUME_KEY = "doppel.volume";
const DEFAULT_VOLUME = 100_000;

function storedVolume(): number {
  try {
    return Number(localStorage.getItem(VOLUME_KEY)) || DEFAULT_VOLUME;
  } catch {
    return DEFAULT_VOLUME;
  }
}

/** Parity-run state shared by the dashboard and presentation mode. */
export function useRun() {
  const [me, setMe] = useState<Me | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<ResultSummary[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [total, setTotal] = useState(0);
  const [identical, setIdentical] = useState(0);
  const [running, setRunning] = useState(false);
  const [explaining, setExplaining] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [volume, setVolumeState] = useState(storedVolume);
  const [stale, setStale] = useState(false);

  const load = useCallback((r: Run) => {
    setRun(r);
    setResults(r.results);
    setGroups(r.groups);
    setTotal(r.summary.total);
    setIdentical(r.summary.identical);
  }, []);

  useEffect(() => {
    Promise.all([getMe(), getLatestRun()])
      .then(([m, r]) => {
        setMe(m);
        if (r) load(r);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));
  }, [load]);

  const setVolume = (v: number) => {
    setVolumeState(v);
    try {
      localStorage.setItem(VOLUME_KEY, String(v));
    } catch {
      /* a per-browser convenience only */
    }
  };

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
            setStale(false);
          } else if (e.type === "error") setError(e.detail);
        });
      } catch (err) {
        setError((err as Error).message);
        if (run) load(run);
      } finally {
        setRunning(false);
        setExplaining(0);
      }
    },
    [volume, load, run],
  );

  const byId = useMemo(() => new Map(results.map((r) => [r.id, r])), [results]);
  const active = groups.filter((g) => g.status !== "FIXED");
  const fixed = groups.filter((g) => g.status === "FIXED");
  const summary = run?.summary;
  // The agent projects at the volume used for the run; re-scale on the client when the input changes.
  const scale = summary ? volume / summary.monthly_volume : 1;

  return {
    me, run, results, groups, active, fixed, byId, total, identical, done: results.length, running, explaining,
    loaded, error, setError, volume, setVolume, scale, start, stale, markStale: () => setStale(true),
  };
}

export type RunState = ReturnType<typeof useRun>;
