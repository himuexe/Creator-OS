import { useState } from 'react'
import type { FormEvent } from 'react'
import { Check, Pencil, Play, X } from 'lucide-react'
import { api, errorText, jsonRequest } from './api'
import type { SuggestedClip } from './api'
import { ErrorState, Status } from './components'

export function timecode(seconds: number) {
  const total = Math.floor(Math.max(0, seconds) * 100 + 0.000001)
  const minutes = Math.floor(total / 6000)
  return minutes + ':' + String(Math.floor(total / 100) % 60).padStart(2, '0') + '.' + String(total % 100).padStart(2, '0')
}

interface Props {
  clip: SuggestedClip
  duration: number
  preview: (start: number, end: number) => void
  onSaved: () => void
}

export function ClipReview({ clip, duration, preview, onSaved }: Props) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [title, setTitle] = useState('')
  const [hook, setHook] = useState('')
  const [description, setDescription] = useState('')

  function edit() {
    setStart(String(clip.start))
    setEnd(String(clip.end))
    setTitle(clip.title)
    setHook(clip.hook)
    setDescription(clip.description)
    setError('')
    setEditing(true)
  }
  async function patch(changes: Partial<SuggestedClip>) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api('/segments/' + clip.id, jsonRequest('PATCH', changes))
      setEditing(false)
      onSaved()
    } catch (cause) {
      setError(errorText(cause))
    } finally {
      setBusy(false)
    }
  }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const a = Number(start), b = Number(end)
    if (!start.trim() || !end.trim() || !Number.isFinite(a) || !Number.isFinite(b) || a < 0 || b > duration || a >= b) {
      setError('Choose a start before the end and keep both times within the source duration.')
      return
    }
    void patch({ start: a, end: b, title: title.trim(), hook: hook.trim(), description: description.trim() })
  }
  return <article className="clip-review" aria-label={clip.title}>
    <div className="clip-top"><span className="range-label">{timecode(clip.start)} – {timecode(clip.end)} <span>· {(clip.end - clip.start).toFixed(1)} s</span></span><Status value={clip.status} /></div>
    <h4>{clip.title}</h4>
    {editing ? <form className="clip-editor" onSubmit={save}>
      <label className="field">Title<input required maxLength={240} value={title} onChange={e => setTitle(e.target.value)} /></label>
      <div className="timing-fields">
        <label className="field">Start (seconds)<input type="number" inputMode="decimal" min="0" max={duration} step="any" required value={start} onChange={e => setStart(e.target.value)} /></label>
        <label className="field">End (seconds)<input type="number" inputMode="decimal" min="0" max={duration} step="any" required value={end} onChange={e => setEnd(e.target.value)} /></label>
      </div>
      <label className="field">Hook<textarea required maxLength={1000} rows={2} value={hook} onChange={e => setHook(e.target.value)} /></label>
      <label className="field">Description<textarea required maxLength={3000} rows={2} value={description} onChange={e => setDescription(e.target.value)} /></label>
      <div className="clip-actions"><button className="button primary" disabled={busy}>Save changes</button><button type="button" className="button secondary" disabled={busy} onClick={() => { setError(''); setEditing(false) }}>Cancel</button></div>
    </form> : <>
      <p className="clip-hook">{clip.hook}</p><p className="clip-description">{clip.description}</p>
      <details className="clip-evidence"><summary>Selection details</summary>
        <dl><dt>Topic</dt><dd>{clip.topic}</dd><dt>Reason for selection</dt><dd>{clip.reason}</dd><dt>Source transcript</dt><dd>{clip.transcript_text}</dd></dl>
      </details>
      <div className="clip-actions">
        <button className="button secondary" onClick={() => preview(clip.start, clip.end)}><Play size={14} />Preview clip</button>
        <button className="button secondary" disabled={busy} onClick={edit}><Pencil size={14} />Edit clip</button>
        <div className="review-actions">
          <button className="review-choice accept" disabled={busy || clip.status === 'approved'} onClick={() => void patch({ status: 'approved' })}><Check size={14} />Approve</button>
          <button className="review-choice" disabled={busy || clip.status === 'rejected'} onClick={() => void patch({ status: 'rejected' })}><X size={14} />Reject</button>
        </div>
      </div>
    </>}
    {error && <ErrorState message={error} />}
  </article>
}
