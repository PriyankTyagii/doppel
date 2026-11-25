import { type Paise, percentOf, divideRound } from "./money.ts";

export const SELLER_STATE = "Maharashtra";
export const LATE_FEE_PCT = 2;
export const GST_RATES = [5, 12, 18] as const;

export interface PricedLine {
  qty: number;
  unitPrice: Paise;
  gstRate: number;
}

export interface InvoiceTotals {
  subtotal: Paise;
  tax: Paise;
  discount: Paise;
  total: Paise;
}

export interface GstSplit {
  cgst: Paise;
  sgst: Paise;
  igst: Paise;
}

export const lineAmount = (line: PricedLine): Paise => line.qty * line.unitPrice;

/** States billed with CGST + SGST; every other state is billed IGST. */
export const SAME_STATE = new Set([SELLER_STATE]);

export const isInterstate = (customerState: string): boolean => !SAME_STATE.has(customerState);

/** Discount comes off the taxable value; GST is then charged on each discounted line. */
export function computeTotals(lines: PricedLine[], couponPct: number): InvoiceTotals {
  const subtotal = lines.reduce((sum, line) => sum + lineAmount(line), 0);

  let discount = 0;
  let tax = 0;
  for (const line of lines) {
    const amount = lineAmount(line);
    const lineDiscount = couponPct ? percentOf(amount, couponPct) : 0;
    discount += lineDiscount;
    tax += percentOf(amount - lineDiscount, line.gstRate);
  }

  return { subtotal, tax, discount, total: subtotal - discount + tax };
}

export function splitGst(tax: Paise, interstate: boolean): GstSplit {
  if (interstate) return { cgst: 0, sgst: 0, igst: tax };
  const cgst = divideRound(tax, 2);
  return { cgst, sgst: tax - cgst, igst: 0 };
}

export function lateFee(total: Paise, dueDate: string, paidOn: string): Paise {
  return paidOn > dueDate ? percentOf(total, LATE_FEE_PCT) : 0;
}

export interface RefundAmount {
  amount: Paise;
  tax: Paise;
}

export function computeRefund(line: PricedLine, qty: number, couponPct: number): RefundAmount {
  const gross = qty * line.unitPrice;
  const taxable = gross - (couponPct ? percentOf(gross, couponPct) : 0);
  const tax = percentOf(taxable, line.gstRate);
  return { amount: taxable + tax, tax };
}
