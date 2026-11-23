import { useCallback, useEffect, useRef, useState } from 'react'
import { AudioLines, Captions, ListVideo, RefreshCw } from 'lucide-react'
import { activeJob, api, errorText } from './api'
import type { Job, Source, SourceAnalysis } from './api'
import { ErrorState, Status } from './components'
import { useData } from './hooks'
import { ClipReview, timecode } from './ClipReview'
import './video-analysis.css'

export function VideoAnalysis({ source, jobsChanged }: { source: Source; jobsChanged: () => void }) {
  const path = '/sources/' + source.id
  const load = useCallback((signal: AbortSignal) => api<SourceAnalysis>(path + '/analysis', { signal }), [path])
  const { value: analysis, error, refresh } = useData(load)
  const [watched, setWatched] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [pollError, setPollError] = useState('')
  const [playError, setPlayError] = useState('')
  const [activeCue, setActiveCue] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  const stopAt = useRef<number | null>(null)
  const frame = useRef(0)
  const transcript = analysis?.transcript
  const job = watched || analysis?.job
  const working = activeJob(job)
  const jobId = job?.id
  const { width, height, duration_seconds, frame_rate, audio_streams } = source.metadata

  useEffect(() => {
    if (!working || !jobId) return
    const controller = new AbortController()
    let timer: number
    async function poll() {
      try {
        const next = await api<Job>('/jobs/' + jobId, { signal: controller.signal })
        if (controller.signal.aborted) return
        setWatched(next)
        setPollError('')
        if (!activeJob(next)) {
          refresh()
          jobsChanged()
          return
        }
      } catch (cause) {
        if (controller.signal.aborted) return
        setPollError(errorText(cause))
      }
      timer = window.setTimeout(poll, 2000)
    }
    timer = window.setTimeout(poll, 500)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [working, jobId, refresh, jobsChanged])

  async function action(endpoint: string) {
    if (busy) return
    setBusy(true)
    setActionError('')
    setPollError('')
    try {
      const next = await api<Job>(endpoint, { method: 'POST' })
      setWatched(next)
      refresh()
      jobsChanged()
    } catch (cause) {
      setActionError(errorText(cause))
      refresh()
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => () => cancelAnimationFrame(frame.current), [])
  function enforceEnd() {
    const video = videoRef.current
    const end = stopAt.current
    if (!video || end === null || video.currentTime < end) return
    stopAt.current = null
    video.pause()
    video.currentTime = end
    cancelAnimationFrame(frame.current)
  }
  function trackPreview() {
    cancelAnimationFrame(frame.current)
    if (!videoRef.current || videoRef.current.paused || stopAt.current === null) return
    enforceEnd()
    if (stopAt.current !== null) frame.current = requestAnimationFrame(trackPreview)
  }
  function seek(start: number, end?: number) {
    const video = videoRef.current
    if (!video) return
    setPlayError('')
    stopAt.current = end ?? null
    try {
      video.pause()
      video.currentTime = start
      if (end !== undefined) {
        video.scrollIntoView({ block: 'nearest' })
        void video.play().catch(() => setPlayError('Preview could not start. Try the video controls or download the original.'))
      }
    } catch {
      setPlayError('The video is not ready to seek. Try again once its metadata has loaded.')
    }
  }
  const hasSpeech = Boolean(transcript?.segments.length)
  return <>
    <div className={'analysis-media' + (hasSpeech ? ' with-transcript' : '')}>
      <div className="player-column">
        <video ref={videoRef} aria-label={'Preview ' + source.filename} controls preload="metadata" src={source.content_url}
          onError={() => setPlayError('This browser could not play the source. Download it to preview locally.')}
          onPlaying={trackPreview}
          onPause={() => cancelAnimationFrame(frame.current)}
          onTimeUpdate={event => {
            enforceEnd()
            const time = event.currentTarget.currentTime
            const cue = transcript?.segments.find(segment => time >= segment.start && time < segment.end)
            setActiveCue(cue?.id || '')
          }} />
        {playError && <p role="status" className="preview-note">{playError}</p>}
        <dl className="media-data">
          {[
            ['Resolution', width && height ? width + ' × ' + height : '—'],
            ['Duration', duration_seconds == null ? '—' : timecode(duration_seconds)],
            ['Frame rate', frame_rate == null ? '—' : Number(frame_rate.toFixed(2)) + ' fps'],
            ['Audio streams', String(audio_streams ?? '—')],
          ].map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      </div>
      {hasSpeech && transcript && <section className="transcript-pane" aria-label="Timestamped transcript">
        <div className="transcript-heading"><h3><Captions size={18} />Transcript</h3><span>{transcript.language} · {transcript.model}</span></div>
        <ol className="transcript-lines">{transcript.segments.map(cue => <li key={cue.id}>
          <button className="transcript-cue" type="button" aria-current={cue.id === activeCue ? 'true' : undefined} onClick={() => seek(cue.start)}>
            <time>{timecode(cue.start)}</time><span>{cue.text}</span>
          </button>
        </li>)}</ol>
      </section>}
    </div>
    <section className="analysis-section" aria-label="Video analysis">
      <div className="analysis-head"><h3><AudioLines size={17} />Video analysis</h3>{job && <Status value={job.status} />}</div>
      {error && <ErrorState message={error} retry={refresh} />}
      {!analysis && !error && <p className="analysis-note" role="status">Loading analysis…</p>}
      {analysis && !job && <div className="analysis-start">
        <p className="analysis-note">{audio_streams === 0 ? 'This source has no audio stream to transcribe.' : 'Transcribe the audio and find passages to review as clips.'}</p>
        <button className="button primary" disabled={busy || audio_streams === 0} onClick={() => void action(path + '/analyze')}><AudioLines size={15} />Analyze video</button>
      </div>}
      {working && job && <div className="job-progress">
        <div role="status"><span>{job.status === 'queued' ? 'Waiting for the worker' : job.stage.replaceAll('_', ' ')}</span><strong>{job.progress}%</strong></div>
        <progress aria-label="Analysis progress" max="100" value={job.progress} />
        <button className="text-btn" disabled={busy} onClick={() => void action('/jobs/' + job.id + '/cancel')}>Cancel job</button>
      </div>}
      {pollError && <p role="status" className="analysis-note">Reconnecting to the worker. {pollError}</p>}
      {job?.status === 'failed' && <div className="analysis-start"><p role="alert" className="analysis-note">{job.error || 'Analysis failed.'}</p><button className="button secondary" disabled={busy} onClick={() => void action('/jobs/' + job.id + '/retry')}><RefreshCw size={14} />Retry analysis</button></div>}
      {job?.status === 'cancelled' && <div className="analysis-start"><p className="analysis-note">Processing was cancelled.</p><button className="button secondary" disabled={busy} onClick={() => void action('/jobs/' + job.id + '/retry')}>Restart analysis</button></div>}
      {job?.status === 'succeeded' && !hasSpeech && transcript && <p className="analysis-note">No speech was detected in this source.</p>}
      {analysis && analysis.topics.length > 0 && <div className="analysis-topics" aria-label="Identified topics">{analysis.topics.map(topic => <span key={topic}>{topic}</span>)}</div>}
      {actionError && <ErrorState message={actionError} />}
    </section>
    {analysis && (hasSpeech || analysis.clips.length > 0) && <section className="recommendations" aria-label="Clip recommendations">
      <div className="recommendation-head">
        <div><h3><ListVideo size={18} />Clip recommendations <small className="count">{analysis.clips.length}</small></h3>
          {analysis.provider && <p className="analysis-note">Suggestions from {analysis.provider}{analysis.model ? ' · ' + analysis.model : ''}</p>}</div>
        <button className="button secondary" disabled={working || busy} onClick={() => void action(path + '/alternatives')}><RefreshCw size={14} />Find alternatives</button>
      </div>
      {analysis.clips.map(clip => <ClipReview key={clip.id} clip={clip} duration={duration_seconds ?? 0} preview={seek} onSaved={refresh} />)}
      {analysis.clips.length === 0 && !working && <p className="analysis-note">No clip suggestions are available for this transcript.</p>}
    </section>}
  </>
}
