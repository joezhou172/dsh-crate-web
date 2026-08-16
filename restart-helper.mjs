import { spawn } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { openSync } from 'node:fs'
import { dirname } from 'node:path'

const encoded = process.argv[2]
if (!encoded) process.exit(2)

const spec = JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'))
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))

async function writeReport(value) {
  await mkdir(dirname(spec.reportPath), { recursive: true })
  await writeFile(spec.reportPath, `${JSON.stringify(value, null, 2)}\n`, { encoding: 'utf8' })
}

function alive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

async function waitForExit(pid, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (alive(pid) && Date.now() < deadline) await sleep(250)
  return !alive(pid)
}

async function httpReady(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2000) })
      if (response.status >= 200 && response.status < 300) return true
    } catch {
      // The new DSH listener may need a few seconds to bind.
    }
    await sleep(500)
  }
  return false
}

async function logTail(path) {
  try {
    const value = await readFile(path, 'utf8')
    return value.slice(-12000)
  } catch {
    return ''
  }
}

await writeReport({
  status: 'pending',
  operationId: spec.operationId,
  stage: 'stopping',
  oldProfile: spec.oldProfile,
  targetProfile: spec.targetProfile,
  message: 'Waiting for the previous DSH process to exit.',
})

if (!(await waitForExit(spec.oldPid, 30000))) {
  await writeReport({
    status: 'failed', code: 'PROFILE_SWITCH_STOP_TIMEOUT', stage: 'stop',
    operationId: spec.operationId, oldProfile: spec.oldProfile, targetProfile: spec.targetProfile,
    item: String(spec.oldPid), expected: 'the previous DSH process exits', observed: 'the previous process is still running',
    evidence: { pid: spec.oldPid }, impact: 'The target Profile was not started.', canContinue: false,
    suggestedNextStep: 'Stop the current DSH process and retry switching the Profile.',
    message: 'Timed out while stopping the previous DSH process.',
  })
  process.exit(1)
}

await writeReport({
  status: 'pending',
  operationId: spec.operationId,
  stage: 'boot',
  oldProfile: spec.oldProfile,
  targetProfile: spec.targetProfile,
  message: 'Starting the target Profile.',
})

const stdoutPath = `${spec.reportPath}.stdout.log`
const stderrPath = `${spec.reportPath}.stderr.log`
const stdout = openSync(stdoutPath, 'a')
const stderr = openSync(stderrPath, 'a')
const child = spawn(spec.nodePath, [spec.scriptPath, ...spec.args], {
  cwd: spec.cwd,
  env: spec.env,
  detached: true,
  windowsHide: true,
  stdio: ['ignore', stdout, stderr],
})
child.unref()

const ready = await httpReady(spec.url, 60000)
if (ready) {
  await writeReport({
    status: 'ready', code: 'PROFILE_SWITCH_READY', stage: 'ready',
    operationId: spec.operationId, oldProfile: spec.oldProfile, targetProfile: spec.targetProfile,
    pid: child.pid, url: spec.url, expected: 'the target DSH Profile is ready', observed: 'HTTP ready response received',
    evidence: { pid: child.pid, url: spec.url }, impact: 'The DSH runtime is now using the target Profile.', canContinue: true,
    suggestedNextStep: 'Continue using the DSH runtime.', message: 'Profile switched and DSH restarted successfully.',
  })
  process.exit(0)
}

await writeReport({
  status: 'failed', code: 'PROFILE_SWITCH_BOOT_FAILED', stage: 'boot',
  operationId: spec.operationId, oldProfile: spec.oldProfile, targetProfile: spec.targetProfile,
  pid: child.pid, item: spec.targetProfile, expected: 'the target DSH Profile becomes HTTP ready', observed: 'HTTP ready was not detected',
  evidence: { pid: child.pid, url: spec.url, stdout: await logTail(stdoutPath), stderr: await logTail(stderrPath) },
  impact: 'The target Profile could not be started or did not become ready.', canContinue: false,
  suggestedNextStep: 'Review stderr and verify the target Profile composition, then retry.',
  message: 'The target Profile failed to become ready.',
})
try { process.kill(child.pid) } catch { /* already stopped */ }
process.exit(1)
