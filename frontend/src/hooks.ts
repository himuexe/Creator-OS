import { useCallback, useEffect, useState } from 'react'
import { errorText } from './api'

export function useRoute() {
  const getRoute = () => window.location.hash.replace(/^#\/?/, '') || 'dashboard'
  const [route, setRoute] = useState(getRoute)
  useEffect(() => {
    const move = () => {
      setRoute(getRoute())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', move)
    return () => window.removeEventListener('hashchange', move)
  }, [])
  return route
}

export function useData<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0)
  const [value, setValue] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    load(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setValue(result)
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(errorText(reason))
          setValue(null)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [load, revision])
  const refresh = useCallback(() => setRevision((revision) => revision + 1), [])
  return { value, error, loading, refresh }
}
