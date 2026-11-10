import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { packageManagerEnvironment } from './pnpm-offline-config.mjs'

const pnpm = resolve(dirname(fileURLToPath(import.meta.url)), '../../node_modules/pnpm/bin/pnpm.mjs')
Object.assign(process.env, packageManagerEnvironment())
process.argv[1] = pnpm
await import(pathToFileURL(pnpm).href)
