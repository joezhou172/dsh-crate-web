/** 只解析配置，不求值 !!js；按映射键与 Cordis row id 合并。 */
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
const require = createRequire(join(process.argv[2], 'package.json'))
const { parseDocument, isMap, isSeq, isAlias, visit } = require('yaml')
const input = JSON.parse(readFileSync(0, 'utf8'))
const parse = text => {
  const doc = parseDocument(text, { uniqueKeys: true, customTags: [{ tag: 'tag:yaml.org,2002:js', resolve: value => value }] })
  if (doc.errors.length) throw Error('配置语法错误，未合并')
  if (doc.warnings.length) throw Error('配置含不支持的标签，未合并')
  visit(doc, (_, node) => { if (isAlias(node)) throw Error('配置含 YAML 引用，需先展开后合并') })
  return doc
}
if (input.operation === 'exclude-plugins') {
  const names = new Set(input.names)
  const ids = new Set()
  const belongs = name => typeof name === 'string' && [...names].some(pkg => name === pkg || name.startsWith(pkg + '/'))
  const collect = node => {
    if (isSeq(node)) for (const item of node.items) collect(item)
    if (isMap(node)) {
      // A patch can modify an official row; its id does not imply ownership.
      if (belongs(node.get('name')) && typeof node.get('id') === 'string') ids.add(node.get('id'))
      for (const key of ['insert', 'config']) if (isSeq(node.get(key, true))) collect(node.get(key, true))
    }
  }
  for (const patch of input.bundlePatches ?? []) collect(parse(patch).contents)
  const prune = node => {
    if (!isSeq(node)) return
    node.items = node.items.filter(row => !isMap(row) || (!belongs(row.get('name')) && !ids.has(row.get('id'))))
    for (const row of node.items) if (isMap(row)) {
      prune(row.get('insert', true))
      if (row.get('group')) prune(row.get('config', true))
    }
  }
  const files = {}
  for (const [name, text] of Object.entries(input.files)) {
    const doc = parse(text)
    if (doc.contents && !isSeq(doc.contents)) throw Error('Loader configuration must be a sequence')
    prune(doc.contents); files[name] = doc.toString()
  }
  process.stdout.write(JSON.stringify({ files }))
  process.exit(0)
}
const target = parse(input.target), source = parse(input.source)
function merge(a, b, depth = 0) {
  if (depth > 64) throw Error('配置嵌套过深')
  if (isMap(a) && isMap(b)) {
    for (const pair of b.items) {
      const key = String(pair.key.value)
      if (['__proto__', 'constructor', 'prototype'].includes(key)) throw Error('不支持的配置键')
      if (a.has(key)) a.set(key, merge(a.get(key, true), pair.value, depth + 1))
      else a.set(key, pair.value?.clone() ?? null)
    }
    return a
  }
  if (isSeq(a) && isSeq(b) && [...a.items, ...b.items].every(row => isMap(row) && typeof row.get('id') === 'string')) {
    for (const seq of [a, b]) if (new Set(seq.items.map(row => row.get('id'))).size !== seq.items.length) throw Error('配置包含重复 row id')
    for (const row of b.items) {
      const index = a.items.findIndex(old => old.get('id') === row.get('id'))
      if (index < 0) a.items.push(row.clone())
      else a.items[index] = merge(a.items[index], row, depth + 1)
    }
    return a
  }
  return input.mode === 'add' ? a : b?.clone() ?? null
}
target.contents = merge(target.contents, source.contents)
process.stdout.write(JSON.stringify({ content: target.toString() }))
