import { type DependencyList, useCallback, useEffect, useState } from "react";

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  /** Replaces the data with a fresh server response (e.g. a mutation that returns the updated list). */
  setData: (data: T) => void;
}

/** Loads `loader()` on mount and whenever `deps` change; a stale response never overwrites a newer one. */
export function useResource<T>(loader: () => Promise<T>, deps: DependencyList): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(loader, deps);

  useEffect(() => {
    let active = true;
    setLoading(true);
    load()
      .then((value) => {
        if (!active) return;
        setData(value);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Không tải được dữ liệu.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load, version]);

  return { data, error, loading, reload: () => setVersion((value) => value + 1), setData };
}

export function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Đã có lỗi xảy ra. Vui lòng thử lại.";
}
