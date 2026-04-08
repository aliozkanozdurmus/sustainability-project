import { z } from "zod";

export const toneSchema = z.enum(["good", "attention", "critical", "neutral"]);
export const healthBandSchema = z.enum(["green", "amber", "red"]);
export const supportTierSchema = z.enum(["certified", "beta", "unsupported"]);
export const userRoleSchema = z.enum([
  "admin",
  "compliance_manager",
  "analyst",
  "auditor_readonly",
  "board_member",
]);

export const nullableStringSchema = z.string().nullable().optional();
export const jsonObjectSchema = z.record(z.string(), z.unknown());
