type Json = Record<string, unknown>
const object = (value: unknown): value is Json => !!value && typeof value === 'object' && !Array.isArray(value)

/** Do not expose response bodies: an upstream error page may contain credentials. */
export async function readApiResponse(response: Response, action: string): Promise<Json> {
  const details = { action, httpStatus: response.status, contentType: response.headers.get('content-type') ?? '', responseCharacters: 0 }
  const failed = (code: string, message: string): Json => ({ status: 'failed', error: { code, stage: 'api-response', message, details } })
  let text: string
  try { text = await response.text() }
  catch { return failed('API_RESPONSE_INTERRUPTED', `DSH Crate response was interrupted (action=${action}, HTTP ${response.status}). Operation outcome is unknown; check history before retrying an import.`) }
  details.responseCharacters = text.length
  let value: unknown
  try { value = JSON.parse(text) } catch { /* Keep HTTP evidence instead of a JSON parser error. */ }
  if (object(value)) return value
  if (response.status === 401 || response.status === 403) return failed('API_ACCESS_REJECTED', `DSH rejected access to Crate (action=${action}, HTTP ${response.status}). Reopen Crate from the current DSH window and check its connection status.`)
  if (response.status === 503) return failed('API_SERVICE_UNAVAILABLE', `DSH Crate service is unavailable (action=${action}, HTTP 503). Check plugin loading and connection status.`)
  if (!text.trim()) return failed('API_EMPTY_RESPONSE', `DSH Crate returned an empty response (action=${action}, HTTP ${response.status}). Operation outcome is unknown; check history before retrying an import.`)
  return failed('API_INVALID_RESPONSE', `DSH Crate returned an invalid response (action=${action}, HTTP ${response.status}). Operation outcome is unknown; check history before retrying an import.`)
}
