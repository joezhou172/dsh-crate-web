// Only parse static YAML with the host's existing parser. Never evaluate tags.
import { createRequire } from 'node:module'
import { readFile, stat } from 'node:fs/promises'
import { join, isAbsolute } from 'node:path'
const [runtime, filename] = process.argv.slice(2)
if (!runtime || !filename || !isAbsolute(filename)) throw Error('Absolute configuration path required')
if ((await stat(filename)).size > 4 * 1024 * 1024) throw Error('Configuration exceeds 4 MiB')
const require = createRequire(import.meta.url)
const yaml = require(join(runtime, 'node_modules', 'js-yaml'))
const value = yaml.load(await readFile(filename, 'utf8'), { schema: yaml.JSON_SCHEMA })
process.stdout.write(JSON.stringify(value ?? []))
