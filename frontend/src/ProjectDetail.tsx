import { useCallback, useState } from 'react'
import { ArrowDownToLine, ArrowLeft, CalendarDays, FileStack, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, errorText, formatBytes, formatDate } from './api'
import type { Job, Limits, Project, Source } from './api'
import { Empty, ErrorState, Loading, Status, WorkflowIcon } from './components'
import { useData } from './hooks'
import { AddSource, EditProject } from './ProjectForms'
import { JobList, PageTitle } from './Workspace'
import { VideoAnalysis } from './VideoAnalysis'

function ScriptPreview({ source }: { source: Source }) {
  const load = useCallback(
    async (signal: AbortSignal) => {
      const response = await fetch(source.content_url, { signal })
      if (!response.ok) throw new Error('Could not load this script.')
      return response.text()
    },
    [source.content_url],
  )
  const { value, loading, error, refresh } = useData(load)
  return loading ? (
    <Loading />
  ) : error ? (
    <ErrorState message={error} retry={refresh} />
  ) : (
    <pre className="script-preview">{value}</pre>
  )
}
function SourcePreview({ source, jobsChanged }: { source: Source; jobsChanged: () => void }) {
  return (
    <div className="source-preview">
      <div className="preview-head">
        <div>
          <h3>{source.filename}</h3>
          <p>
            {formatBytes(source.size_bytes)} · {formatDate(source.created_at)}
          </p>
        </div>
        <a className="button secondary" download={source.filename} href={source.content_url}>
          <ArrowDownToLine size={15} />
          Download
        </a>
      </div>
      {source.kind === 'script' ? (
        <ScriptPreview source={source} />
      ) : (
        <VideoAnalysis source={source} jobsChanged={jobsChanged} />
      )}
    </div>
  )
}
export function ProjectDetail({ id, initialSource, limits, changed }: { id: string; initialSource?: string; limits: Limits; changed: () => void }) {
  const load = useCallback(
    (signal: AbortSignal) =>
      Promise.all([
        api<Project>('/projects/' + id, { signal }),
        api<Source[]>('/projects/' + id + '/sources', { signal }),
        api<Job[]>('/projects/' + id + '/jobs', { signal }),
      ]),
    [id],
  )
  const { value, error, refresh } = useData(load)
  const [selectedId, select] = useState(initialSource || '')
  const jobsChanged = useCallback(() => {
    refresh()
    changed()
  }, [refresh, changed])
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  if (error)
    return (
      <>
        <a href="#/projects" className="back-link">
          <ArrowLeft size={15} />
          Projects
        </a>
        <ErrorState message={error} retry={refresh} />
      </>
    )
  if (!value) return <Loading />
  const [project, sources, jobs] = value
  const selected = sources.find((s) => s.id === selectedId) || sources[0]
  function complete(message: string) {
    setNotice(message)
    refresh()
    changed()
  }
  async function remove() {
    if (removing) return
    setRemoving(true)
    setActionError('')
    try {
      await api('/projects/' + id, { method: 'DELETE' })
      window.location.hash = '/projects'
      changed()
    } catch (e) {
      setActionError(errorText(e))
      setRemoving(false)
    }
  }
  return (
    <>
      <a href="#/projects" className="back-link">
        <ArrowLeft size={15} />
        Projects
      </a>
      <PageTitle
        title={project.name}
        action={
          <div className="title-actions">
            <button
              className="button secondary"
              onClick={() => {
                setEditing(!editing)
                setDeleting(false)
              }}
            >
              <Pencil size={15} />
              Edit
            </button>
            <button
              className="icon-btn"
              title="Delete project"
              aria-label="Delete project"
              onClick={() => {
                setDeleting(!deleting)
                setEditing(false)
              }}
            >
              <Trash2 size={16} />
            </button>
          </div>
        }
      >
        {project.description}
      </PageTitle>
      <div className="detail-meta">
        <Status value={project.status} />
        <span>
          <WorkflowIcon kind={project.workflow} size={14} />
          {project.workflow === 'video' ? 'Video project' : 'Script project'}
        </span>
        <span>
          <CalendarDays size={14} />
          {formatDate(project.created_at)}
        </span>
      </div>
      {editing && (
        <EditProject
          project={project}
          cancel={() => setEditing(false)}
          done={() => {
            setEditing(false)
            complete('Project updated.')
          }}
        />
      )}
      {deleting && (
        <section className="panel delete-box">
          <h2>Delete this project?</h2>
          <p>This permanently removes the project, its sources and its ingestion history.</p>
          {actionError && <ErrorState message={actionError} />}
          <div className="action-row">
            <button className="button secondary" disabled={removing} onClick={() => setDeleting(false)}>
              Keep project
            </button>
            <button className="button danger" disabled={removing} onClick={remove}>
              Delete permanently
            </button>
          </div>
        </section>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {(adding || !sources.length) && (
        <AddSource
          project={project}
          limits={limits}
          cancel={sources.length ? () => setAdding(false) : undefined}
          added={(source) => {
            select(source.id)
            setAdding(false)
            complete('Source saved.')
          }}
        />
      )}
      <section className="panel section">
        <div className="panel-head">
          <h2>
            Sources <small className="count">{sources.length}</small>
          </h2>
          {sources.length > 0 && !adding && (
            <button
              className="small-link"
              onClick={() => {
                setAdding(true)
                setNotice('')
              }}
            >
              <Plus size={15} />
              Add source
            </button>
          )}
        </div>
        {selected ? (
          <>
            <div className="source-tabs" aria-label="Sources">
              {sources.map((s) => (
                <button key={s.id} aria-pressed={s.id === selected.id} onClick={() => select(s.id)}>
                  <WorkflowIcon kind={s.kind} size={14} />
                  {s.filename}
                </button>
              ))}
            </div>
            <SourcePreview source={selected} key={selected.id} jobsChanged={jobsChanged} />
          </>
        ) : (
          <Empty title="No sources yet" icon={<FileStack size={21} />}>
            Saved source material will appear here.
          </Empty>
        )}
      </section>
      <section className="panel section">
        <div className="panel-head">
          <h2>Processing history</h2>
        </div>
        <JobList jobs={jobs} projects={[project]} />
      </section>
    </>
  )
}
