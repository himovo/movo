#!/usr/bin/env node
const fs = require('node:fs')
const path = require('node:path')
const ts = require(path.join(__dirname, '../apps/admin-web/node_modules/typescript'))

const root = path.resolve(__dirname, '..')
const nonAscii = /[^\x20-\x7e]/
const failures = []

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(dir, entry.name)
    return entry.isDirectory() ? files(file) : [file]
  })
}

for (const app of ['admin-web', 'user-web']) {
  const sourceRoot = path.join(root, 'apps', app, 'src')
  const sourceFiles = files(sourceRoot).filter(file => /\.(ts|tsx|vue)$/.test(file))
  const catalogKeys = new Set()

  for (const file of sourceFiles.filter(file => file.includes(`${path.sep}locales${path.sep}`) && file.endsWith('.ts'))) {
    const source = fs.readFileSync(file, 'utf8')
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true)
    function visit(node) {
      if (ts.isPropertyAssignment(node) && ts.isStringLiteral(node.name)) {
        const key = node.name.text
        if (nonAscii.test(key)) failures.push(`${path.relative(root, file)}: non-ASCII catalog key ${JSON.stringify(key)}`)
        // Locale entries are objects with a language-specific translation.
        if (ts.isObjectLiteralExpression(node.initializer)) {
          const fields = new Set(node.initializer.properties.map(property => property.name?.getText(tree).replace(/^['"]|['"]$/g, '')))
          if (fields.has('zh') || fields.has('zh-CN')) {
            catalogKeys.add(key)
            if (!fields.has(app === 'admin-web' ? 'en-US' : 'en')) {
              failures.push(`${path.relative(root, file)}: missing English translation for ${JSON.stringify(key)}`)
            }
          }
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(tree)
  }

  for (const file of sourceFiles) {
    const source = fs.readFileSync(file, 'utf8')
    const calls = /\bt\(\s*(['"`])((?:\\.|(?!\1)[\s\S])*?)\1/g
    let match
    while ((match = calls.exec(source))) {
      const key = match[2]
      const line = source.slice(0, match.index).split('\n').length
      if (nonAscii.test(key)) failures.push(`${path.relative(root, file)}:${line}: non-ASCII t() key ${JSON.stringify(key)}`)
      else if (!key.includes('${') && !/^\s*\+/.test(source.slice(calls.lastIndex)) && !catalogKeys.has(key)) {
        failures.push(`${path.relative(root, file)}:${line}: missing translation for ${JSON.stringify(key)}`)
      }
    }
  }
}

if (failures.length) {
  console.error(failures.join('\n'))
  process.exitCode = 1
} else {
  console.log('Admin and user web locale keys and static t() calls are valid.')
}
