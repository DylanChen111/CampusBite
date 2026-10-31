import { defineConfig } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
const infoPath = fileURLToPath(new URL('../.tools/dev-server.json', import.meta.url))
const info = existsSync(infoPath) ? JSON.parse(readFileSync(infoPath, 'utf8').replace(/^\uFEFF/, '')) : {}
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: [['list'], ['json', { outputFile: process.env.CAMPUSBITE_EVIDENCE ? `${process.env.CAMPUSBITE_EVIDENCE}/browser_results.json` : '../docs/evidence/round03/browser_results.json' }]],
  use: {
    baseURL: process.env.CAMPUSBITE_URL || info.frontend_url || 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 1000 },
    launchOptions: existsSync(edge) ? { executablePath: edge } : {},
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
