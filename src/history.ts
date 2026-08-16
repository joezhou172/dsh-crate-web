import { randomUUID } from 'node:crypto'
import { readFile, rename, unlink, writeFile } from 'node:fs/promises'

export type HistoryItem = Record<string, unknown>
const historyLocks = new Map<string, Promise<void>>()

async function withHistoryLock<T>(path: string, operation: () => Promise<T>): Promise<T> {
  const previous = historyLocks.get(path) ?? Promise.resolve()
  let release!: () => void
  const current = new Promise<void>(resolve => { release = resolve })
  historyLocks.set(path, current)
  await previous
  try {
    return await operation()
  } finally {
    release()
    if (historyLocks.get(path) === current) historyLocks.delete(path)
  }
}

async function readHistoryUnlocked(path: string): Promise<HistoryItem[]> {
  try {
    const value: unknown = JSON.parse(await readFile(path, 'utf8'))
    return Array.isArray(value)
      ? value.filter((item): item is HistoryItem => item !== null && typeof item === 'object' && !Array.isArray(item))
      : []
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}

async function writeHistoryAtomically(path: string, entries: HistoryItem[]): Promise<void> {
  const temporary = `${path}.${randomUUID()}.tmp`
  await writeFile(temporary, `${JSON.stringify(entries, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' })
  try {
    await rename(temporary, path)
  } catch (error) {
    await unlink(temporary).catch(() => undefined)
    throw error
  }
}

export async function readHistory(path: string): Promise<HistoryItem[]> {
  return withHistoryLock(path, () => readHistoryUnlocked(path))
}

export async function record(path: string, item: HistoryItem): Promise<HistoryItem> {
  return withHistoryLock(path, async () => {
    const next = [...await readHistoryUnlocked(path), item].slice(-100)
    await writeHistoryAtomically(path, next)
    return item
  })
}
