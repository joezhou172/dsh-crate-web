/** 绑定原包和导入范围的派生包；预检和执行读取同一份制品。 */
import { createHash } from 'node:crypto'
import { lstat, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

type Body = Record<string, unknown>
const digest = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex')
export function choiceScope(body: Body) {
  const mode = body.choiceMode ?? body.incremental ?? (body.overwrite === true ? 'overwrite' : 'new')
  if (!['new', 'overwrite', 'add', 'update'].includes(String(mode))) throw Error('Invalid import choice mode')
  return { mode, target: mode === 'new' ? null : body.targetProfile ?? null,
    policy: body.compatibilityPolicy === 'strict' ? 'strict' : 'compatible' }
}
export async function sealChoices(work: string, id: string, source: string, prepared: string, body: Body) {
  const receipt = { scope: choiceScope(body), source: digest(await readFile(source)),
    prepared: digest(await readFile(prepared)), expires: Date.now() + 24 * 60 * 60 * 1000 }
  await writeFile(join(work, `import-choice-${id}.json`), JSON.stringify(receipt), { flag: 'wx', mode: 0o600 })
}
export async function selectedPack(work: string, source: string, body: Body) {
  if (body.replacementId === undefined || body.replacementId === '') return source
  if (typeof body.replacementId !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(body.replacementId)) throw Error('Invalid import choice ID')
  const prefix = join(work, `import-choice-${body.replacementId}`)
  for (const file of [prefix + '.json', prefix + '.dshcrate']) {
    const info = await lstat(file)
    if (!info.isFile() || info.isSymbolicLink()) throw Error('Invalid prepared import file')
  }
  const receipt = JSON.parse(await readFile(prefix + '.json', 'utf8'))
  if (Date.now() > receipt.expires || JSON.stringify(receipt.scope) !== JSON.stringify(choiceScope(body)) ||
      digest(await readFile(source)) !== receipt.source || digest(await readFile(prefix + '.dshcrate')) !== receipt.prepared) {
    throw Error('导入包、目标或选择已变化，请重新准备换版方案。 / Import selection changed; prepare it again.')
  }
  return prefix + '.dshcrate'
}
