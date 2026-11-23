export type Workflow = 'video' | 'script'

export interface Project {
  id: string
  name: string
  description: string
  workflow: Workflow
  status: 'draft' | 'ready'
  created_at: string
  updated_at: string
  source_count: number
}
export interface Source {
  id: string
  project_id: string
  kind: Workflow
  filename: string
  media_type: string
  size_bytes: number
  created_at: string
  content_url: string
  metadata: {
    width?: number
    height?: number
    duration_seconds?: number
    frame_rate?: number
    audio_streams?: number
  }
}
export interface Job {
  id: string
  project_id: string
  source_id: string
  kind: 'ingest' | 'analyze' | 'alternatives'
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  stage: string
  progress: number
  attempt: number
  error: string | null
  created_at: string
  finished_at: string | null
}
export const activeJob = (job?: Job | null) => job?.status === 'running' || job?.status === 'queued'

export interface TranscriptSegment {
  id: string
  position: number
  start: number
  end: number
  text: string
}
export interface Transcript {
  id: string
  language: string
  provider: string
  model: string
  segments: TranscriptSegment[]
}
export interface SuggestedClip {
  id: string
  source_id: string
  title: string
  hook: string
  description: string
  topic: string
  reason: string
  start: number
  end: number
  transcript_text: string
  status: 'suggested' | 'approved' | 'rejected'
}
export interface SourceAnalysis {
  source_id: string
  job: Job | null
  transcript: Transcript | null
  topics: string[]
  provider: string | null
  model: string | null
  clips: SuggestedClip[]
}
export interface Limits {
  max_video_bytes: number
  max_script_bytes: number
}

function detail(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return fallback
  const detail = payload.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean)
    if (messages.length) return messages.join('. ')
  }
  return fallback
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch('/api/v1' + path, { cache: 'no-store', ...init })
  if (!response.ok) {
    const message = detail(
      await response.json().catch(() => null),
      'Request failed (' + response.status + ').',
    )
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export function jsonRequest(method: string, value: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }
}

export function upload(projectId: string, file: File, progress: (percent: number) => void): Promise<Source> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/v1/projects/' + encodeURIComponent(projectId) + '/sources')
    xhr.responseType = 'json'
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) progress(Math.round((event.loaded * 100) / event.total))
    }
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve(xhr.response)
        : reject(new Error(detail(xhr.response, 'Upload failed (' + xhr.status + ').')))
    xhr.onerror = () =>
      reject(new Error('Connection lost during upload. Check your source list before retrying.'))
    xhr.onabort = () => reject(new Error('Upload interrupted.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 ** 2) return Number((bytes / 1024).toFixed(1)) + ' KiB'
  return Number((bytes / 1024 ** 2).toFixed(1)) + ' MiB'
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(
    new Date(iso),
  )
}
export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please retry.'
}
