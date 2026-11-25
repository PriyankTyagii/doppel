/** Money is stored as integer paise; the API speaks rupees with two decimals. */
export type Paise = number;

export const toPaise = (rupees: number): Paise => Math.round(rupees * 100);

export const toRupees = (paise: Paise): number => Math.round(paise) / 100;

/** Integer division rounded half up: divideRound(7, 2) === 4. */
export function divideRound(numerator: number, denominator: number): number {
  const quotient = Math.floor(numerator / denominator);
  const remainder = numerator - quotient * denominator;
  return remainder * 2 >= denominator ? quotient + 1 : quotient;
}

/** Applies a percentage to an amount in paise, rounded half up. */
export const percentOf = (amount: Paise, pct: number): Paise => divideRound(amount * pct, 100);
