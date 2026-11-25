import { db } from "./db.ts";
import { toPaise, toRupees, type Paise } from "./money.ts";
import {
  GST_RATES,
  computeRefund,
  computeTotals,
  isInterstate,
  lateFee,
  splitGst,
  type PricedLine,
} from "./tax.ts";

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
  }
}

export interface CustomerInput {
  name: string;
  state: string;
}

export interface LineItemInput {
  sku: string;
  qty: number;
  unit_price?: number | null;
  gst_rate?: number | null;
}

export interface InvoiceInput {
  customer_id: number;
  items: LineItemInput[];
  coupon_pct?: number | null;
  due_date: string;
}

interface CustomerRow {
  id: number;
  name: string;
  state: string;
}

interface ProductRow {
  sku: string;
  unit_price: number;
  gst_rate: number;
}

interface InvoiceRow {
  id: number;
  customer_id: number;
  state: string;
  coupon_pct: number;
  due_date: string;
  subtotal: Paise;
  tax: Paise;
  discount: Paise;
  total: Paise;
  status: "open" | "paid";
  late_fee: Paise;
  amount_paid: Paise;
  paid_on: string | null;
  refunded: Paise;
  created_at: string;
}

interface LineItemRow {
  id: number;
  sku: string;
  qty: number;
  unit_price: Paise;
  gst_rate: number;
}

interface RefundRow {
  id: number;
  sku: string;
  qty: number;
  amount: Paise;
  tax: Paise;
  created_at: string;
}

const timestamp = (): string => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

const isIsoDate = (value: unknown): value is string =>
  typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value));

function findInvoice(id: number): InvoiceRow {
  const row = db.prepare("SELECT * FROM invoices WHERE id = ?").get(id) as InvoiceRow | undefined;
  if (!row) throw new HttpError(404, "invoice not found");
  return row;
}

export function createCustomer(input: CustomerInput) {
  if (typeof input?.name !== "string" || typeof input?.state !== "string") {
    throw new HttpError(422, "name and state are required");
  }
  const result = db
    .prepare("INSERT INTO customers (name, state) VALUES (?, ?)")
    .run(input.name, input.state);
  return { id: Number(result.lastInsertRowid), name: input.name, state: input.state };
}

function priceLine(item: LineItemInput): PricedLine & { sku: string } {
  const product = db.prepare("SELECT * FROM products WHERE sku = ?").get(item.sku) as
    | ProductRow
    | undefined;
  const unitPrice = item.unit_price != null ? toPaise(item.unit_price) : product?.unit_price;
  const gstRate = item.gst_rate ?? product?.gst_rate;

  if (unitPrice == null || gstRate == null) throw new HttpError(400, `unknown sku ${item.sku}`);
  if (!(GST_RATES as readonly number[]).includes(gstRate)) throw new HttpError(400, "bad gst_rate");
  if (!Number.isInteger(item.qty) || item.qty <= 0) throw new HttpError(400, "bad qty");

  return { sku: item.sku, qty: item.qty, unitPrice, gstRate };
}

export function createInvoice(input: InvoiceInput) {
  const customer = db.prepare("SELECT * FROM customers WHERE id = ?").get(input.customer_id) as
    | CustomerRow
    | undefined;
  if (!customer) throw new HttpError(404, "customer not found");
  if (!input.items?.length) throw new HttpError(400, "no items");
  if (!isIsoDate(input.due_date)) throw new HttpError(400, "bad due_date");

  const lines = input.items.map(priceLine);
  const couponPct = Math.trunc(input.coupon_pct ?? 0);
  const totals = computeTotals(lines, couponPct);

  const result = db
    .prepare(
      `INSERT INTO invoices (customer_id, state, coupon_pct, due_date, subtotal, tax, discount, total, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(
      customer.id,
      customer.state,
      couponPct,
      input.due_date,
      totals.subtotal,
      totals.tax,
      totals.discount,
      totals.total,
      timestamp(),
    );
  const invoiceId = Number(result.lastInsertRowid);

  const insertLine = db.prepare(
    "INSERT INTO line_items (invoice_id, sku, qty, unit_price, gst_rate) VALUES (?, ?, ?, ?, ?)",
  );
  for (const line of lines) insertLine.run(invoiceId, line.sku, line.qty, line.unitPrice, line.gstRate);

  return getInvoice(invoiceId);
}

export function getInvoice(id: number) {
  const invoice = findInvoice(id);
  const lines = db
    .prepare("SELECT * FROM line_items WHERE invoice_id = ? ORDER BY id")
    .all(id) as unknown as LineItemRow[];
  const refunds = db
    .prepare("SELECT * FROM refunds WHERE invoice_id = ? ORDER BY id")
    .all(id) as unknown as RefundRow[];

  const interstate = isInterstate(invoice.state);
  const gst = splitGst(invoice.tax, interstate);

  return {
    id: invoice.id,
    customer_id: invoice.customer_id,
    state: invoice.state,
    interstate,
    items: lines.map((line) => ({
      sku: line.sku,
      qty: line.qty,
      unit_price: toRupees(line.unit_price),
      gst_rate: line.gst_rate,
      amount: toRupees(line.qty * line.unit_price),
    })),
    subtotal: toRupees(invoice.subtotal),
    cgst: toRupees(gst.cgst),
    sgst: toRupees(gst.sgst),
    igst: toRupees(gst.igst),
    tax_total: toRupees(invoice.tax),
    coupon_pct: invoice.coupon_pct,
    discount: toRupees(invoice.discount),
    total: toRupees(invoice.total),
    due_date: invoice.due_date,
    status: invoice.status,
    late_fee: toRupees(invoice.late_fee),
    amount_paid: toRupees(invoice.amount_paid),
    paid_on: invoice.paid_on,
    refunded: toRupees(invoice.refunded),
    refunds: refunds.map((refund) => ({
      id: refund.id,
      sku: refund.sku,
      qty: refund.qty,
      amount: toRupees(refund.amount),
      tax: toRupees(refund.tax),
      created_at: refund.created_at,
    })),
    created_at: invoice.created_at,
  };
}

export function payInvoice(id: number, paidOn: unknown) {
  const invoice = findInvoice(id);
  if (invoice.status !== "open") throw new HttpError(400, "invoice not open");
  if (!isIsoDate(paidOn)) throw new HttpError(400, "bad paid_on");

  const fee = lateFee(invoice.total, invoice.due_date, paidOn);
  db.prepare("UPDATE invoices SET status = 'paid', late_fee = ?, amount_paid = ?, paid_on = ? WHERE id = ?").run(
    fee,
    invoice.total + fee,
    paidOn,
    id,
  );
  return getInvoice(id);
}

export function refundInvoice(id: number, sku: string, qty: number) {
  const invoice = findInvoice(id);
  const line = db
    .prepare("SELECT * FROM line_items WHERE invoice_id = ? AND sku = ?")
    .get(id, sku) as LineItemRow | undefined;
  if (!line) throw new HttpError(400, "sku not on invoice");

  const { refundedQty } = db
    .prepare("SELECT COALESCE(SUM(qty), 0) AS refundedQty FROM refunds WHERE invoice_id = ? AND sku = ?")
    .get(id, sku) as { refundedQty: number };
  if (!Number.isInteger(qty) || qty <= 0 || qty + refundedQty > line.qty) {
    throw new HttpError(400, "bad refund qty");
  }

  const refund = computeRefund(
    { qty: line.qty, unitPrice: line.unit_price, gstRate: line.gst_rate },
    qty,
    invoice.coupon_pct,
  );
  db.prepare("INSERT INTO refunds (invoice_id, sku, qty, amount, tax, created_at) VALUES (?, ?, ?, ?, ?, ?)").run(
    id,
    sku,
    qty,
    refund.amount,
    refund.tax,
    timestamp(),
  );
  db.prepare("UPDATE invoices SET refunded = refunded + ? WHERE id = ?").run(refund.amount, id);
  return getInvoice(id);
}
