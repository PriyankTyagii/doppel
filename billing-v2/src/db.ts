import { DatabaseSync } from "node:sqlite";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CUSTOMERS, GST_BY_CATEGORY, PRODUCTS } from "./seed.ts";
import { toPaise } from "./money.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const dbPath = process.env.BILLING_DB ?? path.join(here, "..", "billing.db");

export const db = new DatabaseSync(dbPath);

const SCHEMA = `
  DROP TABLE IF EXISTS refunds;
  DROP TABLE IF EXISTS line_items;
  DROP TABLE IF EXISTS invoices;
  DROP TABLE IF EXISTS products;
  DROP TABLE IF EXISTS customers;

  CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL
  );
  CREATE TABLE products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit_price INTEGER NOT NULL,
    gst_rate INTEGER NOT NULL
  );
  CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    state TEXT NOT NULL,
    coupon_pct INTEGER NOT NULL DEFAULT 0,
    due_date TEXT NOT NULL,
    subtotal INTEGER NOT NULL,
    tax INTEGER NOT NULL,
    discount INTEGER NOT NULL,
    total INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    late_fee INTEGER NOT NULL DEFAULT 0,
    amount_paid INTEGER NOT NULL DEFAULT 0,
    paid_on TEXT,
    refunded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
  );
  CREATE TABLE line_items (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    gst_rate INTEGER NOT NULL
  );
  CREATE TABLE refunds (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    tax INTEGER NOT NULL,
    created_at TEXT NOT NULL
  );
`;

export function resetDatabase(): void {
  db.exec(SCHEMA);
  const insertCustomer = db.prepare("INSERT INTO customers (name, state) VALUES (?, ?)");
  for (const customer of CUSTOMERS) insertCustomer.run(customer.name, customer.state);

  const insertProduct = db.prepare(
    "INSERT INTO products (sku, name, unit_price, gst_rate) VALUES (?, ?, ?, ?)",
  );
  for (const product of PRODUCTS) {
    insertProduct.run(product.sku, product.name, toPaise(product.unitPrice), GST_BY_CATEGORY[product.category]);
  }
}

export function ensureDatabase(): void {
  const row = db
    .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'invoices'")
    .get();
  if (!row) resetDatabase();
}
