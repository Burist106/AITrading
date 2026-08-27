import { z } from "zod";

export const IdentifierSchema = z.string().trim().min(1).max(160);
export const UuidSchema = z.string().uuid();
export const IsoDateTimeSchema = z.string().datetime({ offset: true });
export const FiniteNumberSchema = z.number().finite();
export const PositiveNumberSchema = FiniteNumberSchema.positive();
export const NonNegativeNumberSchema = FiniteNumberSchema.nonnegative();
export const CurrencyCodeSchema = z.string().regex(/^[A-Z]{3}$/u);

export function isBefore(left: string, right: string): boolean {
  return Date.parse(left) < Date.parse(right);
}
