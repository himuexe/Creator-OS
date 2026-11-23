import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Check, FileText, LoaderCircle, Upload, X } from 'lucide-react'
import { api, errorText, formatBytes, jsonRequest, upload } from './api'
import type { Limits, Project, Source, Workflow } from './api'
import { ErrorState, WorkflowIcon } from './components'
import { PageTitle } from './Workspace'

export function NewProject({ initial, changed }: { initial: Workflow; changed: () => void }) {
  const [workflow, setWorkflow] = useState(initial)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  async function create(event: FormEvent) {
    event.preventDefault()
    if (lock.current || !name.trim()) return
    lock.current = true
    setBusy(true)
    setError('')
    try {
      const p = await api<Project>(
        '/projects',
        jsonRequest('POST', { name: name.trim(), description: description.trim(), workflow }),
      )
      window.location.hash = '/projects/' + p.id
      changed()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
      lock.current = false
    }
  }
  return (
    <>
      <a className="back-link" href="#/projects">
        <ArrowLeft size={15} />
        Projects
      </a>
      <PageTitle title="New project">Choose a workflow and give your project a name.</PageTitle>
      <form className="panel editor-form" onSubmit={create}>
        <fieldset disabled={busy}>
          <legend>Workflow</legend>
          <div className="workflow-picker">
            {(['video', 'script'] as const).map((k) => (
              <label className={'choice ' + (workflow === k ? 'selected' : '')} key={k}>
                <input
                  type="radio"
                  name="workflow"
                  value={k}
                  checked={workflow === k}
                  onChange={() => setWorkflow(k)}
                />
                <WorkflowIcon kind={k} size={20} />
                <strong>{k === 'video' ? 'Recorded video' : 'Written script'}</strong>
                {workflow === k && <Check size={14} />}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="field">
          Project name
          <input
            required
            maxLength={120}
            placeholder="e.g. How neural networks learn"
            autoComplete="off"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>
            Description <small>optional</small>
          </span>
          <textarea
            rows={3}
            maxLength={2000}
            placeholder="What is this project about?"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        {error && <ErrorState message={error} />}
        <div className="form-footer">
          <p>You can add your source after creating the project.</p>
          <button className="button primary" disabled={busy || !name.trim()}>
            {busy ? <LoaderCircle size={16} className="spin" /> : <ArrowRight size={16} />}Create project
          </button>
        </div>
      </form>
    </>
  )
}

export function EditProject({
  project,
  done,
  cancel,
}: {
  project: Project
  done: () => void
  cancel: () => void
}) {
  const [name, setName] = useState(project.name)
  const [description, setDescription] = useState(project.description)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function save(event: FormEvent) {
    event.preventDefault()
    if (!name.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      await api(
        '/projects/' + project.id,
        jsonRequest('PATCH', { name: name.trim(), description: description.trim() }),
      )
      done()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="panel editor-form" onSubmit={save}>
      <h2>Edit project</h2>
      <label className="field">
        Project name
        <input value={name} required maxLength={120} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        Description
        <textarea
          value={description}
          maxLength={2000}
          rows={3}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      {error && <ErrorState message={error} />}
      <div className="action-row">
        <button className="button secondary" type="button" onClick={cancel} disabled={busy}>
          Cancel
        </button>
        <button className="button primary" disabled={!name.trim() || busy}>
          Save changes
        </button>
      </div>
    </form>
  )
}

export function AddSource({
  project,
  limits,
  added,
  cancel,
}: {
  project: Project
  limits: Limits
  added: (s: Source) => void
  cancel?: () => void
}) {
  const script = project.workflow === 'script'
  const [mode, setMode] = useState<'write' | 'upload'>(script ? 'write' : 'upload')
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const lock = useRef(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const limit = script ? limits.max_script_bytes : limits.max_video_bytes
  const accept = script ? '.txt,.md' : '.mp4,.mov,.webm,.mkv'
  function choose(f: File | undefined) {
    if (!f) return
    setFile(null)
    if (!accept.split(',').some((ext) => f.name.toLowerCase().endsWith(ext))) {
      setError('Choose a supported file type (' + accept.replaceAll(',', ', ') + ').')
      return
    }
    if (!f.size || f.size > limit) {
      setError('Choose a nonempty file up to ' + formatBytes(limit) + '.')
      return
    }
    setError('')
    setFile(f)
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (lock.current || (mode === 'write' ? !text.trim() : !file)) return
    if (mode === 'write' && new Blob([text]).size > limit) {
      setError('Script exceeds ' + formatBytes(limit) + '.')
      return
    }
    lock.current = true
    setBusy(true)
    setProgress(0)
    setError('')
    try {
      const source =
        mode === 'write'
          ? await api<Source>('/projects/' + project.id + '/scripts', jsonRequest('POST', { text }))
          : await upload(project.id, file!, setProgress)
      added(source)
    } catch (e) {
      setError(errorText(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  return (
    <form className="panel source-form" onSubmit={submit}>
      <div className="panel-head">
        <h2>Add a source</h2>
        {cancel && (
          <button
            type="button"
            disabled={busy}
            className="icon-link"
            aria-label="Close source form"
            onClick={cancel}
          >
            <X size={17} />
          </button>
        )}
      </div>
      <fieldset className="source-inputs" disabled={busy}>
        {script && (
          <div className="switcher" aria-label="Script input method">
            <button
              type="button"
              aria-pressed={mode === 'write'}
              onClick={() => {
                setMode('write')
                setError('')
              }}
            >
              <FileText size={15} />
              Write script
            </button>
            <button
              type="button"
              aria-pressed={mode === 'upload'}
              onClick={() => {
                setMode('upload')
                setError('')
              }}
            >
              <Upload size={15} />
              Upload file
            </button>
          </div>
        )}
        {mode === 'write' ? (
          <label className="field">
            Script text
            <textarea
              required
              rows={7}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste or write your narration here…"
            />
          </label>
        ) : (
          <div
            className={'drop-area ' + (dragging ? 'dragging' : '')}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              if (!busy) choose(e.dataTransfer.files[0])
            }}
          >
            <Upload size={25} />
            <strong>{file ? file.name : 'Drop your ' + (script ? 'script' : 'video') + ' here'}</strong>
            <small>
              {file
                ? formatBytes(file.size)
                : accept.toUpperCase().replaceAll('.', '').replaceAll(',', ', ') +
                  ' · up to ' +
                  formatBytes(limit)}
            </small>
            <button type="button" className="button secondary" onClick={() => fileInput.current?.click()}>
              {file ? 'Choose another file' : 'Choose file'}
            </button>
            <input
              ref={fileInput}
              type="file"
              aria-label="Source file"
              accept={accept}
              hidden
              onChange={(e) => {
                choose(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </div>
        )}
      </fieldset>
      {error && <ErrorState message={error} />}
      {busy && (
        <div className="upload-status" role="status">
          {mode === 'upload' && <progress max={100} value={progress} />}
          <span>
            {mode === 'write'
              ? 'Saving script…'
              : progress === 100
                ? 'Checking source…'
                : 'Uploading ' + progress + '%'}
          </span>
        </div>
      )}
      <div className="action-row">
        <button className="button primary" disabled={busy || (mode === 'write' ? !text.trim() : !file)}>
          {busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}Save source
        </button>
      </div>
    </form>
  )
}
