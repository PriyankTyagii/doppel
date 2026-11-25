export type Status = "NEW" | "FIXED" | "UNCHANGED" | "OK";

export interface FieldDiff {
  path: string;
  field: string;
  v1: unknown;
  v2: unknown;
  delta: number | null;
}

export interface Impact {
  bill_delta: number;
  tax_delta: number;
  direction: "overcharged" | "undercharged" | "none";
}

export interface ResultSummary {
  id: string;
  kind: string;
  summary: string;
  tags: string[];
  match: boolean;
  status: Status;
  diffs: FieldDiff[];
  impact: Impact;
  v1_cached: boolean;
}

export interface Step {
  tool: string;
  args: Record<string, unknown>;
  save_as: string | null;
}

export interface TraceCall {
  system: string;
  tool: string;
  args: Record<string, unknown>;
}

export interface FullResult extends ResultSummary {
  steps: Step[];
  v1: unknown[];
  v2: unknown[];
  trace: TraceCall[];
}

export interface Explanation {
  cause: string;
  rule: string;
  v1_file: string;
  v1_line: number;
  v2_file: string;
  v2_line: number;
  explanation: string;
  suggested_fix: string;
  recent_change: boolean;
  changed_line: string;
  source?: string;
}

export interface GroupImpact {
  invoices_affected: number;
  rupees_wrong: number;
  tax_misreported: number;
  overcharged: number;
  undercharged: number;
  tax_only: number;
  overcharged_rupees: number;
  undercharged_rupees: number;
  projected_monthly_invoices: number;
  projected_monthly_rupees: number;
  projected_monthly_tax: number;
}

export interface Group {
  key: string;
  fields: string[];
  scenario_ids: string[];
  status: "NEW" | "UNCHANGED" | "FIXED";
  origin?: string;
  first_run?: boolean;
  explanation?: Explanation;
  impact?: GroupImpact;
}

export interface Summary {
  identical: number;
  total: number;
  parity_pct: number;
  impact: GroupImpact;
  monthly_volume: number;
  headline: string;
  projection_note: string;
}

export interface Run {
  run_id: string;
  started_at: string;
  duration_s: number;
  v2_commit: string;
  v2_diff: string;
  summary: Summary;
  previous_summary: Summary | null;
  counts: Record<Status, number>;
  groups: Group[];
  results: (ResultSummary & Partial<FullResult>)[];
}

export interface Mutation {
  id: string;
  title: string;
  description: string;
  file: string;
  find: string;
  replace: string;
  changes_endpoints: boolean;
  applied: boolean;
}

export interface ControlState {
  branch: string;
  demo_active: boolean;
  pre_demo_commit: string;
  applied: { id: string; title: string; commit: string; file: string; line: number }[];
  v2_healthy: boolean;
  v2_managed: boolean;
}

export interface Definition {
  file: string;
  name: string;
  start: number;
  end: number;
  source?: string;
}

export interface Me {
  email: string;
  email_verified: boolean;
  is_admin: boolean;
  mode: "http" | "mcp";
  llm: { provider: string; model: string; configured: boolean };
  tools: Record<string, string[]>;
}
