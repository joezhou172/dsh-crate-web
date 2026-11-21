import type { DshCrateLocaleKey } from './locales.ts'
type Json = Record<string, unknown>
export class CrateRequestError extends Error { diagnostic: Json; constructor(diagnostic: Json) }
export function crateRequest(action: string, body?: Json, fetcher?: typeof fetch): Promise<Json>
export function requestFailure(error: unknown): Json
export function requireProfilesResponse(value: Json): Json
export function followUpFailure(error: unknown, stage?: string): Json
export function errorReport(error: unknown): Json
export function errorDisplay(error: unknown, t: (key: DshCrateLocaleKey) => string): string
