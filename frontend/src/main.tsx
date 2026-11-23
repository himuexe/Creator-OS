import { StrictMode, useCallback, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Activity,
  AudioLines,
  ChevronRight,
  CircleUserRound,
  FileText,
  Film,
  FolderClosed,
  LayoutDashboard,
  Menu,
  PanelsTopLeft,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import '@fontsource-variable/inter'
import './studio.css'
import { activeJob, api } from './api'
import type { Job, Limits, Project } from './api'
import { Empty, ErrorState, Loading } from './components'
import { useData, useRoute } from './hooks'
import { NewProject } from './ProjectForms'
import { ProjectDetail } from './ProjectDetail'
import { Dashboard, JobList, PageTitle, Projects } from './Workspace'

type NavItem = [string, string, LucideIcon]
const workspaceNav: NavItem[] = [
  ['dashboard', 'Overview', LayoutDashboard],
  ['projects', 'Projects', FolderClosed],
  ['activity', 'Activity', Activity],
]
const studioNav: NavItem[] = [
  ['studio/video', 'Video studio', Film],
  ['studio/script', 'Script studio', FileText],
]

function App() {
  const route = useRoute()
  const [path, param, sourceId] = route.split('/')
  const [mobileOpen, setMobileOpen] = useState(false)
  const load = useCallback(
    (signal: AbortSignal) =>
      Promise.all([
        api<Project[]>('/projects', { signal }),
        api<Job[]>('/jobs', { signal }),
        api<Limits>('/health', { signal }),
      ]),
    [],
  )
  const data = useData(load)
  const page =
    path === 'new'
      ? 'New project'
      : path === 'projects' && param
        ? 'Project details'
        : [...workspaceNav, ...studioNav].find(([url]) => url === route)?.[1] || 'Page'
  useEffect(() => {
    setMobileOpen(false)
    document.title = page + ' · CreatorOS'
  }, [route, page])
  useEffect(() => {
    if (!mobileOpen) return
    function close(event: KeyboardEvent) {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [mobileOpen])
  const refresh = data.refresh
  const working = data.value?.[1].some(activeJob)
  useEffect(() => {
    if (!working || (path !== 'dashboard' && path !== 'activity')) return
    const timer = window.setInterval(refresh, 3000)
    return () => window.clearInterval(timer)
  }, [working, path, refresh])
  useEffect(() => {
    const update = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [refresh])
  function nav(items: NavItem[]) {
    return items.map(([url, title, Icon]) => {
      const active = route === url || (url === 'projects' && path === 'projects')
      return (
        <a
          key={url}
          className={'nav-link ' + (active ? 'active' : '')}
          aria-current={active ? 'page' : undefined}
          href={'#/' + url}
          onClick={() => setMobileOpen(false)}
        >
          <Icon size={18} />
          {title}
        </a>
      )
    })
  }
  function content() {
    if (data.error)
      return (
        <>
          <PageTitle title="Workspace unavailable" />
          <ErrorState message={'Could not load the studio. ' + data.error} retry={refresh} />
        </>
      )
    if (!data.value) return <Loading />
    const [projects, jobs, limits] = data.value
    if (path === 'dashboard') return <Dashboard projects={projects} jobs={jobs} />
    if (path === 'projects' && param)
      return <ProjectDetail key={route} id={encodeURIComponent(param)} initialSource={sourceId} limits={limits} changed={refresh} />
    if (path === 'projects') return <Projects key={route} projects={projects} />
    if (path === 'studio' && (param === 'video' || param === 'script'))
      return <Projects key={route} projects={projects} studio={param} />
    if (path === 'new')
      return <NewProject key={route} initial={param === 'script' ? 'script' : 'video'} changed={refresh} />
    if (path === 'activity')
      return (
        <>
          <PageTitle title="Activity">Processing history across your projects.</PageTitle>
          <div className="panel">
            <div className="panel-head">
              <h2>Processing jobs</h2>
            </div>
            <JobList projects={projects} jobs={jobs} />
          </div>
        </>
      )
    return (
      <Empty title="Page unavailable">
        <a className="inline-link" href="#/dashboard">
          Return to overview
        </a>
      </Empty>
    )
  }
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault()
          document.getElementById('main-content')?.focus()
        }}
      >
        Skip to content
      </a>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation backdrop"
          className="scrim"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={'sidebar ' + (mobileOpen ? 'open' : '')} id="studio-navigation">
        <div className="brand-row">
          <a className="brand" href="#/dashboard" onClick={() => setMobileOpen(false)}>
            <span className="brand-mark">
              <AudioLines size={22} strokeWidth={2.5} />
            </span>
            <b>
              Creator<span>OS</span>
            </b>
          </a>
          <button
            className="mobile-close icon-link"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X size={19} />
          </button>
        </div>
        <nav aria-label="Primary">
          <p className="nav-label">Workspace</p>
          {nav(workspaceNav)}
          <p className="nav-label second">Studios</p>
          {nav(studioNav)}
        </nav>
        <div className="sidebar-footer">
          <span className="profile-icon">
            <CircleUserRound size={22} />
          </span>
          <div>
            <strong>Personal workspace</strong>
            <small>Local creator</small>
          </div>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="menu-toggle icon-link"
              aria-label="Open navigation"
              aria-expanded={mobileOpen}
              aria-controls="studio-navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={20} />
            </button>
            <PanelsTopLeft size={16} className="desktop-crumb" />
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{page}</strong>
          </div>
          <span className={'connection ' + (data.value ? 'online' : '')}>
            <i />
            {data.error ? 'API offline' : data.value ? 'API connected' : 'Connecting'}
          </span>
        </header>
        <main id="main-content" tabIndex={-1}>
          {content()}
        </main>
      </div>
    </div>
  )
}
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
