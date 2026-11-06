import { useCallback, useEffect, useRef, useState } from "react";

/** Loads data on mount and when deps change. A stale response from an earlier request is ignored. */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const latest = useRef(0);

  const run = useCallback(async () => {
    const ticket = ++latest.current;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await loader();
      if (ticket === latest.current) setState({ data, loading: false, error: null });
      return data;
    } catch (error) {
      if (ticket === latest.current) setState({ data: null, loading: false, error });
      return undefined;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { ...state, reload: run };
}

/** Runs an action on demand, tracking its progress and error for the button that triggered it. */
export function useAction(action) {
  const [state, setState] = useState({ busy: false, error: null });
  const run = useCallback(
    async (...args) => {
      setState({ busy: true, error: null });
      try {
        const result = await action(...args);
        setState({ busy: false, error: null });
        return result;
      } catch (error) {
        setState({ busy: false, error });
        return undefined;
      }
    },
    [action],
  );
  return { ...state, run, clearError: () => setState((current) => ({ ...current, error: null })) };
}
