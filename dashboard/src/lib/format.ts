const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const inrWhole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹1,23,456.70 */
export const rs = (x: number) => `₹${inr.format(x)}`;
/** ₹1,23,457 (projections are estimates; no paise) */
export const rsWhole = (x: number) => `₹${inrWhole.format(x)}`;
export const num = (x: number) => inrWhole.format(x);
export const signed = (x: number) => (x > 0 ? `+${rs(x)}` : x < 0 ? `−${rs(-x)}` : rs(0));

export const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

/** Repo-relative file:line, or nothing when unknown. */
export const loc = (file?: string, line?: number) => (file ? `${file}${line ? `:${line}` : ""}` : "");
