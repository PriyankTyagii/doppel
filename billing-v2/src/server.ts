import express, { type NextFunction, type Request, type Response } from "express";
import { ensureDatabase, resetDatabase } from "./db.ts";
import { CUSTOMERS, PRODUCTS } from "./seed.ts";
import {
  HttpError,
  createCustomer,
  createInvoice,
  getInvoice,
  payInvoice,
  refundInvoice,
  type CustomerInput,
  type InvoiceInput,
} from "./invoices.ts";

const app = express();
app.use(express.json());

const invoiceId = (req: Request): number => {
  const id = Number(req.params.id);
  if (!Number.isInteger(id)) throw new HttpError(422, "invoice id must be an integer");
  return id;
};

app.get("/health", (_req: Request, res: Response) => {
  res.json({ ok: true, service: "billing-v2" });
});

app.post("/reset", (_req: Request, res: Response) => {
  resetDatabase();
  res.json({ ok: true, customers: CUSTOMERS.length, products: PRODUCTS.length });
});

app.post("/customers", (req: Request<{}, unknown, CustomerInput>, res: Response) => {
  res.json(createCustomer(req.body));
});

app.post("/invoices", (req: Request<{}, unknown, InvoiceInput>, res: Response) => {
  res.json(createInvoice(req.body));
});

app.get("/invoices/:id", (req: Request, res: Response) => {
  res.json(getInvoice(invoiceId(req)));
});

app.post("/invoices/:id/pay", (req: Request, res: Response) => {
  res.json(payInvoice(invoiceId(req), req.body?.paid_on));
});

app.post("/invoices/:id/refund", (req: Request, res: Response) => {
  res.json(refundInvoice(invoiceId(req), req.body?.sku, req.body?.qty));
});

app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  if (err instanceof HttpError) {
    res.status(err.status).json({ detail: err.detail });
    return;
  }
  console.error(err);
  res.status(500).json({ detail: "internal error" });
});

ensureDatabase();

const port = Number(process.env.PORT ?? 8002);
app.listen(port, () => console.log(`billing-v2 listening on http://localhost:${port}`));
