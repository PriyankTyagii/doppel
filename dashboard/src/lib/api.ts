import { idToken } from "./auth";
import type { ControlState, Definition, FullResult, Group, Me, Mutation, ResultSummary, Run } from "../types";

const AGENT = import.meta.env.VITE_AGENT_URL ?? "http://localhost:8000";
const CONTROL = import.meta.env.VITE_CONTROL_URL ?? "http://localhost:8090";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function call(base: string, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${await idToken()}`);
  if (init.body) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...init, headers });
  } catch {
    const service = base === AGENT ? "Doppel agent" : "demo control";
    throw new ApiError(`Can't reach the ${service} at ${base}. Is it running?`, 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError((body as { detail?: string }).detail ?? `Request failed (${res.status})`, res.status);
  }
  return res;
}

const get = <T>(base: string, path: string) => call(base, path).then((r) => r.json() as Promise<T>);
const post = <T>(base: string, path: string, body?: unknown) =>
  call(base, path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }).then(
    (r) => r.json() as Promise<T>,
  );

export type RunEvent =
  | { type: "start"; run_id: string; total: number; v1_cached: boolean }
  | { type: "result"; result: ResultSummary; done: number; identical: number }
  | { type: "explaining"; groups: number }
  | { type: "group"; group: Group }
  | { type: "done"; run: Run }
  | { type: "error"; detail: string };

/** POST /run streams server-sent events; EventSource can't POST or send headers, so read the stream directly. */
export async function streamRun(volume: number, fresh: boolean, onEvent: (e: RunEvent) => void): Promise<void> {
  const res = await call(AGENT, `/run?volume=${volume}&fresh=${fresh}`, { method: "POST" });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const data = buffer
        .slice(0, idx)
        .split("\n")
        .find((l) => l.startsWith("data: "));
      buffer = buffer.slice(idx + 2);
      if (data) onEvent(JSON.parse(data.slice(6)) as RunEvent);
    }
  }
}

export const getMe = () => get<Me>(AGENT, "/me");

export async function getLatestRun(): Promise<Run | null> {
  try {
    return await get<Run>(AGENT, "/runs/latest");
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const getScenario = (id: string) => get<FullResult>(AGENT, `/runs/latest/scenarios/${id}`);

export async function downloadReport(): Promise<void> {
  const blob = await (await call(AGENT, "/report.md")).blob();
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: "doppel-parity-report.md" });
  a.click();
  URL.revokeObjectURL(url);
}

export interface AdhocResponse {
  plan: { summary: string; assumptions: string; request: string };
  result: FullResult;
  explanation: (NonNullable<Group["explanation"]> & { reused_from?: string }) | null;
}
export const runAdhoc = (text: string) => post<AdhocResponse>(AGENT, "/adhoc", { text });

export const controlState = () => get<ControlState>(CONTROL, "/state");
export const listMutations = () => get<Mutation[]>(CONTROL, "/mutations");
export const applyMutation = (id: string) => post<Record<string, unknown>>(CONTROL, `/mutations/${id}/apply`);
export const restoreDemo = () => post<Record<string, unknown>>(CONTROL, "/restore");
export const listDefinitions = () => get<Definition[]>(CONTROL, "/definitions");
export const getDefinition = (file: string, name: string) => get<Definition>(CONTROL, `/definitions/${file}/${name}`);
export const checkEdit = (file: string, name: string, source: string) =>
  post<{ ok: boolean; typecheck: string }>(CONTROL, "/edit/check", { file, name, source });
export const applyEdit = (file: string, name: string, source: string) =>
  post<Record<string, unknown>>(CONTROL, "/edit/apply", { file, name, source });
