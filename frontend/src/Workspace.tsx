import { useState } from 'react'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CheckCheck,
  FileStack,
  FolderClosed,
  FolderOpen,
  Layers3,
  Plus,
  Search,
  Timer,
} from 'lucide-react'
import { Empty, ProjectList, Status, StudioCard } from './components'
import { formatTime } from './api'
import type { Job, Project, Workflow } from './api'

export function PageTitle({
  title,
  children,
  action,
}: {
  title: string
  children?: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <header className="page-title">
      <div>
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      {action}
    </header>
  )
}
export function NewLink({ workflow }: { workflow?: Workflow }) {
  return (
    <a className="button primary" href={'#/new' + (workflow ? '/' + workflow : '')}>
      <Plus size={17} />
      New project
    </a>
  )
}
export function JobList({
  jobs,
  projects,
  compact = false,
}: {
  jobs: Job[]
  projects: Project[]
  compact?: boolean
}) {
  if (!jobs.length)
    return (
      <Empty title="No processing activity" icon={<Activity size={22} />}>
        Ingestion history appears when you add a source.
      </Empty>
    )
  return (
    <ul className={'job-list ' + (compact ? 'compact' : '')}>
      {jobs.map((j) => {
        const p = projects.find((project) => project.id === j.project_id)
        const operation = { ingest: 'Source ingestion', analyze: 'Video analysis', alternatives: 'Alternative suggestions' }[j.kind]
        return (
          <li key={j.id}>
            <a className="job-row" href={'#/projects/' + j.project_id + '/' + j.source_id}>
              <span className={'job-icon ' + j.status}>
                {j.status === 'succeeded' ? <CheckCheck size={17} /> : j.status === 'failed' ? <AlertCircle size={17} /> : <Timer size={17} />}
              </span>
              <div className="row-name">
                <strong>{compact ? operation : p?.name || operation}</strong>
                <small>
                  {compact ? p?.name || 'Project source' : operation} · {formatTime(j.created_at)}
                </small>
              </div>
              {(!compact || j.status !== 'succeeded') && <Status value={j.status} />}
            </a>
          </li>
        )
      })}
    </ul>
  )
}
export function Dashboard({ projects, jobs }: { projects: Project[]; jobs: Job[] }) {
  const metrics = [
    { label: 'Projects', value: projects.length, icon: FolderClosed },
    {
      label: 'Source files',
      value: projects.reduce((total, p) => total + p.source_count, 0),
      icon: FileStack,
    },
    { label: 'Processing jobs', value: jobs.length, icon: Activity },
  ]
  return (
    <>
      <PageTitle title="Studio overview" action={<NewLink />}>
        Your projects, source material and production activity.
      </PageTitle>
      <div className="metrics">
        {metrics.map(({ label, value, icon: Icon }) => (
          <div key={label} className="metric">
            <span className="metric-label">{label}</span>
            <strong>{value}</strong>
            <div className="metric-icon">
              <Icon size={18} />
            </div>
          </div>
        ))}
      </div>
      <section className="section">
        <h2>Start a production</h2>
        <div className="studios">
          <StudioCard kind="video" />
          <StudioCard kind="script" />
        </div>
      </section>
      <div className="dashboard-lower">
        <section className="panel">
          <div className="panel-head">
            <h2>Recent projects</h2>
            <a href="#/projects" className="small-link">
              View all <ArrowRight size={13} />
            </a>
          </div>
          {projects.length ? (
            <ProjectList projects={projects.slice(0, 5)} />
          ) : (
            <Empty title="Your first project starts here">
              Choose a studio above to add a video or script.
            </Empty>
          )}
        </section>
        <section className="panel activity-panel">
          <div className="panel-head">
            <h2>Recent activity</h2>
            <a aria-label="View all activity" className="icon-link" href="#/activity">
              <ArrowRight size={16} />
            </a>
          </div>
          <JobList jobs={jobs.slice(0, 4)} projects={projects} compact />
        </section>
      </div>
    </>
  )
}
export function Projects({ projects, studio }: { projects: Project[]; studio?: Workflow }) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('')
  const filtered = projects.filter(
    (p) =>
      (!studio || studio === p.workflow) &&
      (!kind || kind === p.workflow) &&
      p.name.toLowerCase().includes(query.trim().toLowerCase()),
  )
  const title = studio === 'video' ? 'Video studio' : studio === 'script' ? 'Script studio' : 'Projects'
  return (
    <>
      <PageTitle title={title} action={<NewLink workflow={studio} />}>
        {studio === 'video'
          ? 'Projects built from recorded footage.'
          : studio === 'script'
            ? 'Projects built from written scripts.'
            : 'Browse and manage your production projects.'}
      </PageTitle>
      <div className="panel">
        <div className="tool-row">
          <label className="search">
            <Search size={16} />
            <input
              aria-label="Search projects"
              placeholder="Search projects"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {!studio && (
            <select value={kind} aria-label="Filter workflows" onChange={(e) => setKind(e.target.value)}>
              <option value="">All workflows</option>
              <option value="video">Video</option>
              <option value="script">Script</option>
            </select>
          )}
        </div>
        {filtered.length ? (
          <ProjectList projects={filtered} />
        ) : (
          <Empty
            icon={studio ? <Layers3 size={22} /> : <FolderOpen size={22} />}
            title={query || kind ? 'No matching projects' : 'No projects yet'}
          >
            {query || kind ? (
              'Try another name or workflow.'
            ) : (
              <a href={'#/new' + (studio ? '/' + studio : '')} className="inline-link">
                Create your first project
              </a>
            )}
          </Empty>
        )}
      </div>
    </>
  )
}
