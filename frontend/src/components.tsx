import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import {
  AlertCircle,
  ArrowRight,
  Check,
  ChevronRight,
  FileText,
  Film,
  FolderOpen,
  LoaderCircle,
} from 'lucide-react'
import type { Project, Workflow } from './api'
import { formatDate } from './api'

export function WorkflowIcon({ kind, size = 18 }: { kind: Workflow; size?: number }) {
  return kind === 'video' ? <Film size={size} /> : <FileText size={size} />
}
export function Status({ value }: { value: string }) {
  return (
    <span className={'status ' + value}>
      {value === 'ready' || value === 'succeeded' ? <Check size={12} /> : <span className="status-dot" />}
      {value === 'ready'
        ? 'Source ready'
        : value === 'draft'
          ? 'Draft'
          : value === 'succeeded'
            ? 'Completed'
            : value.charAt(0).toUpperCase() + value.slice(1)}
    </span>
  )
}
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div role="alert" className="error-state">
      <AlertCircle size={17} />
      <span>{message}</span>
      {retry && (
        <button type="button" className="text-btn" onClick={retry}>
          Retry
        </button>
      )}
    </div>
  )
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={18} className="spin" /> Loading workspace…
    </div>
  )
}
export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon || <FolderOpen size={22} />}</div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  )
}
export function ProjectList({ projects }: { projects: Project[] }) {
  return (
    <ul className="project-list">
      {projects.map((p) => (
        <li key={p.id}>
          <a className="project-row" href={'#/projects/' + p.id}>
            <span className={'media-icon ' + p.workflow}>
              <WorkflowIcon kind={p.workflow} />
            </span>
            <span className="row-name">
              <strong>{p.name}</strong>
              <small>
                {p.workflow === 'video' ? 'Video project' : 'Script project'} · {p.source_count}{' '}
                {p.source_count === 1 ? 'source' : 'sources'}
              </small>
            </span>
            <Status value={p.status} />
            <time dateTime={p.updated_at}>{formatDate(p.updated_at)}</time>
            <ChevronRight size={16} />
          </a>
        </li>
      ))}
    </ul>
  )
}

// A spectrogram-style fold and a typeset manuscript visually distinguish the two inputs.
function WaveArt() {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const draw = () => {
      const width = canvas.clientWidth,
        height = canvas.clientHeight
      const scale = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = width * scale
      canvas.height = height * scale
      const ctx = canvas.getContext('2d')
      if (!ctx || !width || !height) return
      ctx.scale(scale, scale)
      for (let row = 0; row < 55; row++) {
        const depth = row / 54
        ctx.beginPath()
        for (let x = -1; x <= width + 2; x += 2) {
          const t = x / width
          const phase = 4.5 * t + 1.9 * depth
          const shoulder = Math.exp(-((t - 0.66) ** 2) / 0.1)
          const y =
            height *
            (0.39 +
              0.62 * depth +
              0.17 * Math.sin(phase + 2.5) +
              shoulder * (0.41 * Math.sin(phase * 2.1 + depth * 0.9) + 0.095 * Math.sin(phase * 4.1)))
          if (x < 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        const light = Math.sin(depth * Math.PI)
        ctx.strokeStyle =
          'rgba(' +
          Math.round(139 + 69 * light) +
          ',' +
          Math.round(90 + 53 * light) +
          ',255,' +
          (0.3 + 0.52 * light) +
          ')'
        ctx.lineWidth = 0.75
        ctx.stroke()
      }
    }
    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    draw()
    return () => observer.disconnect()
  }, [])
  return <canvas ref={ref} />
}

export function StudioCard({ kind }: { kind: Workflow }) {
  const video = kind === 'video'
  return (
    <a className={'studio-card ' + kind} href={'#/new/' + kind}>
      <div className="card-art" aria-hidden="true">
        {video ? (
          <WaveArt />
        ) : (
          <div className="manuscript">
            <div className="sheet sheet-back" />
            <div className="sheet sheet-mid" />
            <div className="sheet sheet-front">
              <b>Aa</b>
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>
        )}
        <span className="art-icon">
          <WorkflowIcon kind={kind} size={18} />
        </span>
      </div>
      <div className="studio-copy">
        <div>
          <h3>{video ? 'Video studio' : 'Script studio'}</h3>
          <p>{video ? 'Start with a recorded video.' : 'Start with a written script.'}</p>
        </div>
        <span className="circle-arrow">
          <ArrowRight size={16} />
        </span>
      </div>
    </a>
  )
}
