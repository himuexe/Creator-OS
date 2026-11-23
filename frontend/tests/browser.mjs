import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

export const studio = new URL(process.env.CREATOROS_TEST_URL || 'http://127.0.0.1:5173')
if (!['127.0.0.1', 'localhost', '[::1]'].includes(studio.hostname)) {
  throw new Error('Use a local test workspace.')
}

export function launchBrowser() {
  const candidates = process.platform === 'win32'
    ? [
      join(process.env.ProgramFiles || '', 'Google/Chrome/Application/chrome.exe'),
      join(process.env['ProgramFiles(x86)'] || '', 'Microsoft/Edge/Application/msedge.exe'),
    ]
    : ['/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
  return chromium.launch({ executablePath: process.env.CREATOROS_BROWSER || candidates.find(existsSync), headless: true })
}
