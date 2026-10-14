import { useCallback, useEffect, useRef, useState, type DependencyList } from "react"
import { isAbortError, normalizeError, type ApiError } from "../lib/errors"

export interface AsyncResult<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  /** Re-run the loader, aborting any request already in flight. */
  run: () => Promise<T | null>
  /** Replace the current data locally (optimistic updates). */
  setData: (updater: T | null | ((previous: T | null) => T | null)) => void
  setError: (error: ApiError | null) => void
}

/**
 * Run an abortable async loader on mount and whenever `deps` change.
 *
 * The loader receives an `AbortSignal` that is cancelled on unmount, on a deps
 * change, and when `run()` is called again — so no stale response can overwrite
 * newer state.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList = [],
  options: { immediate?: boolean; initialData?: T | null } = {},
): AsyncResult<T> {
  const { immediate = true, initialData = null } = options

  const [data, setDataState] = useState<T | null>(initialData)
  const [error, setErrorState] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(immediate)

  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const controllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [])

  const run = useCallback(async (): Promise<T | null> => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setLoading(true)
    setErrorState(null)

    try {
      const result = await loaderRef.current(controller.signal)
      if (!mountedRef.current || controller.signal.aborted) return null
      setDataState(result)
      return result
    } catch (caught) {
      if (!mountedRef.current || controller.signal.aborted || isAbortError(caught)) return null
      setErrorState(normalizeError(caught))
      return null
    } finally {
      if (mountedRef.current && !controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!immediate) return
    void run()
    return () => controllerRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  const setData = useCallback((updater: T | null | ((previous: T | null) => T | null)) => {
    setDataState((previous) =>
      typeof updater === "function" ? (updater as (value: T | null) => T | null)(previous) : updater,
    )
  }, [])

  return { data, error, loading, run, setData, setError: setErrorState }
}
