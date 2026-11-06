import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { isSafeProfileName } from '../src/profile-name.ts'
const cases = JSON.parse(await readFile(new URL('./profile_names.json', import.meta.url), 'utf8'))
for (const name of cases.valid) assert.equal(isSafeProfileName(name), true, name)
for (const name of [...cases.invalid, null, undefined, 1]) assert.equal(isSafeProfileName(name), false, String(name))
console.log('PASS: Profile names accept Unicode and spaces; reject unsafe paths and reserved names')
