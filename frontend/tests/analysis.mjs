// Set CREATOROS_TEST_SPEECH to a browser-playable MP4 with an educational speech passage.
// This workflow starts real worker jobs in the local studio.
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { basename } from 'node:path'
import { launchBrowser, studio } from './browser.mjs'

const speech = process.env.CREATOROS_TEST_SPEECH
if (!speech) throw new Error('Set CREATOROS_TEST_SPEECH to a video containing spoken educational content.')
const timeout = Number(process.env.CREATOROS_TEST_ANALYSIS_TIMEOUT_MS || 10 * 60 * 1000)
const endpoint = (path) => new URL('/api/v1' + path, studio).href
const json = (value) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })
const name = 'Analysis browser test ' + randomUUID().slice(0, 8)
let projectId
let browser
try {
  const response = await fetch(endpoint('/projects'), json({ name, workflow: 'video' }))
  assert.equal(response.status, 201)
  projectId = (await response.json()).id
  const form = new FormData()
  form.set('file', new Blob([await readFile(speech)], { type: 'video/mp4' }), basename(speech))
  const uploaded = await fetch(endpoint('/projects/' + projectId + '/sources'), { method: 'POST', body: form })
  assert.equal(uploaded.status, 201)
  const source = await uploaded.json()
  const sourcePath = endpoint('/sources/' + source.id)
  browser = await launchBrowser()
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } })
  const errors = []
  page.on('pageerror', (cause) => errors.push(cause.message))

  // One transient read error exercises the retry UI before using the real analyzer.
  await page.route(sourcePath + '/analysis', route => route.fulfill({
    status: 503, json: { detail: 'Analysis temporarily unavailable' },
  }))
  await page.goto(new URL('#/projects/' + projectId + '/' + source.id, studio).href)
  const panel = page.getByRole('region', { name: 'Video analysis', exact: true })
  await panel.getByRole('alert').waitFor()
  await page.unroute(sourcePath + '/analysis')
  await panel.getByRole('button', { name: 'Retry', exact: true }).click()
  const jobResponse = page.waitForResponse(r => r.url() === sourcePath + '/analyze' && r.request().method() === 'POST')
  await panel.getByRole('button', { name: 'Analyze video' }).click()
  assert.equal((await jobResponse).status(), 202)
  await panel.getByText(/^(completed|failed)$/i).waitFor({ timeout })
  if (await panel.getByRole('alert').count()) throw new Error(await panel.getByRole('alert').innerText())

  const current = async () => {
    const result = await fetch(sourcePath + '/analysis')
    assert.equal(result.status, 200)
    return result.json()
  }
  const analysis = await current()
  assert.equal(analysis.job.status, 'succeeded')
  assert.ok(analysis.transcript.segments.length > 0, 'Expected a timestamped transcription')
  assert.ok(analysis.clips.length > 0, 'Expected a clip suggestion for the speech fixture')
  const cue = analysis.transcript.segments.find(segment => segment.start > 0) || analysis.transcript.segments[0]
  await page.getByRole('region', { name: 'Timestamped transcript' }).getByRole('button').nth(cue.position).click()
  await page.waitForFunction(
    start => Math.abs(document.querySelector('video').currentTime - start) < 0.06, cue.start,
  )
  const clip = analysis.clips[0]
  const article = page.getByRole('article', { name: clip.title, exact: true }).first()
  await article.getByText('Selection details', { exact: true }).click()
  await article.getByText(clip.transcript_text, { exact: true }).waitFor()
  await article.getByRole('button', { name: 'Edit clip' }).click()
  await article.getByLabel('Title', { exact: true }).fill(name + ' reviewed')
  const editedEnd = Math.min(clip.end, clip.start + 1.25)
  await article.getByLabel('End (seconds)').fill(String(editedEnd))
  await article.getByRole('button', { name: 'Save changes' }).click()
  const reviewed = page.getByRole('article', { name: name + ' reviewed', exact: true })
  await reviewed.getByRole('button', { name: 'Preview clip' }).click()
  await page.waitForFunction(
    end => {
      const v = document.querySelector('video')
      return v.paused && Math.abs(v.currentTime - end) < 0.06
    }, editedEnd, { timeout: 15000 },
  )
  await reviewed.getByRole('button', { name: 'Reject', exact: true }).click()
  await reviewed.getByText('Rejected', { exact: true }).waitFor()
  await reviewed.getByRole('button', { name: 'Approve', exact: true }).click()
  await reviewed.getByText('Approved', { exact: true }).waitFor()
  await page.reload()
  await reviewed.getByText('Approved', { exact: true }).waitFor()
  assert.equal((await current()).clips.find(item => item.id === clip.id).end, editedEnd)

  const alternativeJob = page.waitForResponse(r => r.url() === sourcePath + '/alternatives' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Find alternatives' }).click()
  const alternativeResponse = await alternativeJob
  assert.equal(alternativeResponse.status(), 202)
  const id = (await alternativeResponse.json()).id
  // Watch the submitted job ID specifically; a fast worker can finish between two paints.
  await page.waitForResponse(async r => {
    if (!r.ok() || !r.url().endsWith('/jobs/' + id)) return false
    const job = await r.json()
    return ['succeeded', 'failed', 'cancelled'].includes(job.status)
  }, { timeout }).catch(async cause => {
    const latest = (await current()).job
    if (latest.id !== id || latest.status !== 'succeeded') throw cause
  })
  const final = await current()
  assert.equal(final.job.status, 'succeeded', final.job.error)
  assert.ok(final.clips.some(item => item.id === clip.id && item.status === 'approved' && item.end === editedEnd))
  await page.setViewportSize({ width: 390, height: 844 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile overflow')
  assert.deepEqual(errors, [])
  console.log('PASS real analysis, transcript seek, clip evidence, bounded preview, edited timing, review persistence, alternatives and mobile layout')
  console.log('Source duration: ' + source.metadata.duration_seconds + ' s; transcript segments: ' + analysis.transcript.segments.length + '; initial clips: ' + analysis.clips.length)
} finally {
  await browser?.close()
  if (projectId) {
    const removed = await fetch(endpoint('/projects/' + projectId), { method: 'DELETE' })
    assert.ok([204, 404].includes(removed.status), 'Temporary project cleanup failed')
  }
}
