import type { ControlState, Definition, FullResult, Group, Mutation, ResultSummary, Run } from "./types";

export const AGENT = import.meta.env.VITE_AGENT_URL ?? "http://localhost:8000";
export const CONTROL = import.meta.env.VITE_CONTROL_URL ?? "http://localhost:8090";

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  return body as T;
}

export type RunEvent =
  | { type: "start"; run_id: string; total: number; v1_cached: boolean }
  | { type: "result"; result: ResultSummary; done: number; identical: number }
  | { type: "explaining"; groups: number }
  | { type: "group"; group: Group }
  | { type: "done"; run: Run }
  | { type: "error"; detail: string };

/** POST /run streams server-sent events; EventSource is GET-only, so read the stream by hand. */
export async function streamRun(volume: number, fresh: boolean, onEvent: (e: RunEvent) => void): Promise<void> {
  const res = await fetch(`${AGENT}/run?volume=${volume}&fresh=${fresh}`, { method: "POST" });
  if (!res.ok || !res.body) throw new Error((await res.json().catch(() => ({}))).detail ?? `HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const data = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)) as RunEvent);
    }
  }
}

export const getLatestRun = () => fetch(`${AGENT}/runs/latest`).then((r) => (r.ok ? (r.json() as Promise<Run>) : null));
export const getScenario = (id: string) => fetch(`${AGENT}/runs/latest/scenarios/${id}`).then((r) => json<FullResult>(r));
export const agentHealth = () => fetch(`${AGENT}/health`).then((r) => json<{ mode: string; tools: Record<string, string[]> }>(r));
export const reportUrl = () => `${AGENT}/report.md`;

export interface AdhocResponse {
  plan: { summary: string; assumptions: string; request: string };
  result: FullResult;
  explanation: (Group["explanation"] & { reused_from?: string }) | null;
}
export const runAdhoc = (text: string) =>
  fetch(`${AGENT}/adhoc`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }) }).then(
    (r) => json<AdhocResponse>(r),
  );

export const controlState = () => fetch(`${CONTROL}/state`).then((r) => json<ControlState>(r));
export const listMutations = () => fetch(`${CONTROL}/mutations`).then((r) => json<Mutation[]>(r));
export const applyMutation = (id: string) =>
  fetch(`${CONTROL}/mutations/${id}/apply`, { method: "POST" }).then((r) => json<Record<string, unknown>>(r));
export const restoreDemo = () => fetch(`${CONTROL}/restore`, { method: "POST" }).then((r) => json<Record<string, unknown>>(r));
export const listDefinitions = () => fetch(`${CONTROL}/definitions`).then((r) => json<Definition[]>(r));
export const getDefinition = (file: string, name: string) =>
  fetch(`${CONTROL}/definitions/${file}/${name}`).then((r) => json<Definition>(r));
const post = (path: string, body: unknown) =>
  fetch(`${CONTROL}${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
export const checkEdit = (file: string, name: string, source: string) =>
  post("/edit/check", { file, name, source }).then((r) => json<{ ok: boolean; typecheck: string }>(r));
export const applyEdit = (file: string, name: string, source: string) =>
  post("/edit/apply", { file, name, source }).then((r) => json<Record<string, unknown>>(r));
