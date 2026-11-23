// Exercise a running local studio with real storage, API calls, and a synthetic video.
// Set CREATOROS_TEST_VIDEO to reuse a small, browser-playable MP4 instead of generating one.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { studio as url, launchBrowser } from './browser.mjs'

const directory = mkdtempSync(join(tmpdir(), 'creatoros-browser-'))
const ids = []
let browser
try {
  const media = process.env.CREATOROS_TEST_VIDEO || join(directory, 'lesson.mp4')
  if (!process.env.CREATOROS_TEST_VIDEO) {
    execFileSync(process.env.FFMPEG_BIN || 'ffmpeg', [
      '-hide_banner',
      '-loglevel',
      'error',
      '-f',
      'lavfi',
      '-i',
      'testsrc2=s=320x180:r=24',
      '-f',
      'lavfi',
      '-i',
      'sine=frequency=440',
      '-t',
      '1',
      '-threads',
      '1',
      '-c:v',
      'libx264',
      '-pix_fmt',
      'yuv420p',
      '-c:a',
      'aac',
      media,
    ])
  }
  browser = await launchBrowser()
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } })
  const exceptions = []
  page.on('pageerror', (e) => exceptions.push(e.message))
  await page.goto(url.href)
  await page.getByRole('heading', { name: 'Studio overview' }).waitFor()
  const run = 'Browser test ' + randomUUID().slice(0, 8)

  async function create(kind) {
    await page.goto(new URL('#/dashboard', url).href)
    await page.locator('.studio-card.' + kind).click()
    await page.getByLabel('Project name').fill(run + ' ' + kind)
    const created = page.waitForResponse(
      (r) => r.url().endsWith('/api/v1/projects') && r.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Create project' }).click()
    const response = await created
    assert.equal(response.status(), 201)
    const { id } = await response.json()
    ids.push(id)
    await page.getByRole('heading', { name: run + ' ' + kind, exact: true }).waitFor()
    return id
  }
  async function saveSource(endpoint) {
    const saved = page.waitForResponse((r) => r.url().endsWith(endpoint) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Save source' }).click()
    return saved
  }
  const scriptId = await create('script')
  const script = 'Every neuron receives inputs and combines them with learned weights.'
  await page.getByLabel('Script text').fill(script)
  assert.equal((await saveSource('/scripts')).status(), 201)
  await page.getByText(script, { exact: true }).waitFor()
  await page.reload()
  await page.getByText(script, { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByLabel('Project name').fill(run + ' revised')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await page.getByRole('heading', { name: run + ' revised' }).waitFor()
  await page.getByRole('button', { name: 'Add source' }).click()
  await page.getByRole('button', { name: 'Upload file' }).click()
  await page
    .getByLabel('Source file', { exact: true })
    .setInputFiles({ name: 'outline.md', mimeType: 'text/markdown', buffer: Buffer.from('# Lesson outline') })
  assert.equal((await saveSource('/sources')).status(), 201)
  await page.getByText('# Lesson outline', { exact: true }).waitFor()
  console.log('PASS script creation, direct input, reload, editing and Markdown upload')

  const videoId = await create('video')
  await page.getByLabel('Source file', { exact: true }).setInputFiles(media)
  await page.getByLabel('Source file', { exact: true }).setInputFiles({
    name: 'outline.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('A script cannot replace a video.'),
  })
  assert.ok(await page.getByRole('button', { name: 'Save source' }).isDisabled())
  await page
    .getByLabel('Source file', { exact: true })
    .setInputFiles({ name: 'invalid.mp4', mimeType: 'video/mp4', buffer: Buffer.from('invalid test media') })
  assert.equal((await saveSource('/sources')).status(), 422)
  await page.getByRole('alert').waitFor()
  assert.ok(page.url().endsWith(videoId))
  await page.getByLabel('Source file', { exact: true }).setInputFiles(media)
  const uploaded = await saveSource('/sources')
  assert.equal(uploaded.status(), 201)
  const source = await uploaded.json()
  await page.getByRole('heading', { name: source.filename, exact: true }).waitFor()
  await page.waitForFunction(() => {
    const video = document.querySelector('video')
    return video && video.videoWidth > 0 && video.duration > 0
  })
  const display = await page
    .locator('video')
    .evaluate((v) => ({ width: v.videoWidth, height: v.videoHeight, duration: v.duration }))
  assert.equal(display.width, source.metadata.width)
  assert.equal(display.height, source.metadata.height)
  assert.ok(Math.abs(display.duration - source.metadata.duration_seconds) < 0.4)
  assert.ok(source.metadata.audio_streams > 0)
  assert.equal(
    (await (await page.request.get(new URL('/api/v1/projects/' + videoId + '/jobs', url).href)).json())
      .length,
    1,
  )
  console.log(
    'PASS rejected upload, retry in original project, verified playable video and ingestion history',
  )

  await page.goto(new URL('#/projects', url).href)
  await page.getByLabel('Search projects').fill(run)
  await page.getByLabel('Filter workflows').selectOption('script')
  await page.getByRole('link', { name: new RegExp(run + ' revised') }).click()
  assert.ok(page.url().endsWith(scriptId))
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Activity', exact: true }).click()
  await page.getByRole('heading', { name: 'Activity' }).waitFor()
  await page
    .getByRole('link', { name: new RegExp(run + ' revised') })
    .first()
    .waitFor()
  await page.goto(new URL('#/dashboard', url).href)
  await page.getByRole('heading', { name: 'Studio overview' }).waitFor()
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await page.goto(new URL('#/projects/' + scriptId, url).href)
  await page.getByRole('button', { name: 'Delete project', exact: true }).click()
  await page.getByRole('button', { name: 'Delete permanently' }).click()
  await page.getByRole('heading', { name: 'Projects', exact: true }).waitFor()
  assert.equal((await page.request.get(new URL('/api/v1/projects/' + scriptId, url).href)).status(), 404)
  assert.deepEqual(exceptions, [])
  console.log('PASS search, workflow filter, activity, mobile navigation, deletion and browser error check')
} finally {
  try {
    for (const id of ids) {
      const response = await fetch(new URL('/api/v1/projects/' + id, url), { method: 'DELETE' })
      if (![204, 404].includes(response.status)) throw new Error('Test cleanup failed for project ' + id)
    }
  } finally {
    await browser?.close()
    rmSync(directory, { recursive: true, force: true })
  }
}
