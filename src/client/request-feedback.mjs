export class CrateRequestError extends Error {
  constructor(diagnostic) { super(JSON.stringify(diagnostic, null, 2)); this.name = 'CrateRequestError'; this.diagnostic = diagnostic; }
}
export async function crateRequest(action, body = {}, fetcher = globalThis.fetch) {
  const startedAt = new Date().toISOString();
  const requestId = globalThis.crypto?.randomUUID?.() ?? `local-${Date.now()}`;
  const writeRequested = action === 'import' && body.planOnly !== true;
  let response;
  const fail = (stage, code) => { throw new CrateRequestError({
    producer: 'dsh-crate', diagnosticSchemaVersion: 1, operation: action,
    requestId, startedAt, observedAt: new Date().toISOString(), stage, code,
    httpStatus: response?.status ?? null, contentType: response?.headers.get('content-type') ?? null,
    status: 'FAIL', scope: 'request', writeRequested,
    requestKind: action === 'import' && body.planOnly === true ? 'import-plan' : action,
    operationOutcome: writeRequested ? 'UNKNOWN' : 'UNTESTED',
    automaticRetry: false,
    message: writeRequested ? 'Import result is unknown. Check the maintenance result and target environment before any further import.' : `Request ${action} failed; previously confirmed import results remain unchanged.`,
    messageZh: writeRequested ? '未取得有效导入结果；请检查维护结果和目标环境，不要重复导入。' : `请求 ${action} 失败；不改变已经确认的导入结果。`,
  }); };
  try { response = await fetcher('/dsh-crate/api', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...body, action }) }); }
  catch { fail('transport', 'REQUEST_TRANSPORT_FAILED'); }
  let text;
  try { text = await response.text(); } catch { fail('response-read', 'RESPONSE_READ_FAILED'); }
  if (!text.trim()) fail('response-empty', 'EMPTY_RESPONSE');
  let value;
  try { value = JSON.parse(text); } catch { fail('response-json', 'INVALID_JSON'); }
  if (!value || typeof value !== 'object' || Array.isArray(value) || typeof value.status !== 'string') fail('response-shape', 'INVALID_RESPONSE');
  const requestDiagnostic = { operation: action, httpStatus: response.status,
    startedAt, observedAt: new Date().toISOString(), requestId, stage: 'http',
    contentType: response.headers.get('content-type'), automaticRetry: false };
  if (!response.ok) {
    if (value.status === 'failed' || value.status === 'FAIL') return { ...value, requestDiagnostic };
    fail('http', 'HTTP_ERROR');
  }
  return { ...value, requestDiagnostic };
}
export function requestFailure(error) {
  if (error instanceof CrateRequestError) return {
    status: error.diagnostic.writeRequested === true ? 'UNKNOWN' : 'failed',
    scope: 'request', operation: error.diagnostic.operation, error: error.diagnostic,
  };
  return { status: 'failed', error: { message: String(error) } };
}
export function requireProfilesResponse(value) {
  if (value?.status === 'ok' && Array.isArray(value.profiles) &&
      value.runtime && typeof value.runtime === 'object' && !Array.isArray(value.runtime) &&
      Array.isArray(value.runtimePlugins)) return value;
  const metadata = value?.requestDiagnostic ?? {};
  throw new CrateRequestError({
    ...metadata, producer: 'dsh-crate', diagnosticSchemaVersion: 1, operation: 'profiles',
    stage: 'profile-refresh', code: 'PROFILE_REFRESH_FAILED',
    status: 'FAIL', scope: 'request', operationOutcome: 'UNTESTED', writeRequested: false,
    automaticRetry: false, serverReport: value,
    message: 'Environment refresh failed. The previously displayed environment list is retained.',
    messageZh: '环境刷新失败，保留此前显示的环境列表。',
  });
}
export function followUpFailure(error, stage = 'post-import-refresh') {
  return { status: 'DEGRADED', scope: 'post-import', stage,
    importOutcome: 'PREPARED', knownImportResultPreserved: true,
    error: requestFailure(error),
    message: 'Import completed; environment refresh failed. The import result is retained.',
    messageZh: '导入已经完成；环境刷新失败，原导入结果已保留。',
  };
}
export function errorReport(error) {
  if (error instanceof CrateRequestError) return requestFailure(error);
  const text = String(error).replace(/^(?:CrateRequestError|Error):\s*/, '');
  try {
    const value = JSON.parse(text);
    if (value?.scope === 'post-import' && value.status === 'DEGRADED') return value;
    if (value?.scope === 'request' && value.error?.producer === 'dsh-crate') return value;
    if (value?.producer === 'dsh-crate' && value.scope === 'request') return requestFailure(new CrateRequestError(value));
  } catch { /* Ordinary user-visible messages remain ordinary errors. */ }
  return { status: 'failed', error: { message: String(error) } };
}
export function errorDisplay(error, t) {
  const report = errorReport(error);
  if (report.scope === 'post-import') return t('postImportRefreshFailed');
  if (report.scope === 'request') return t(report.status === 'UNKNOWN' ? 'importOutcomeUnknown' : 'requestFailed');
  return String(error);
}
