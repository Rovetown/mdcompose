import { Cache } from "./cache.ts";
import type { Failure, Result } from "./result.ts";

// What a view shows for one report.
//   cached       read from the cache at start, before any refresh finished
//   fresh        just read from the command line
//   stale        a refresh failed, so the last good read is shown with the error
//   unavailable  no cache and the refresh failed
export type Snapshot<T> =
  | { state: "cached"; value: T; readAt: string }
  | { state: "fresh"; value: T; readAt: string }
  | { state: "stale"; value: T; readAt: string; error: Failure }
  | { state: "unavailable"; error: Failure };

export function fromCache<T>(cache: Cache, name: string, key: string): Snapshot<T> | null {
  const entry = cache.load<T>(name, key);
  if (entry === null) return null;
  return { state: "cached", value: entry.value, readAt: entry.savedAt };
}

export interface RefreshOptions<T> {
  cache: Cache;
  name: string;
  key: string;
  now: () => Date;
  read: () => Promise<Result<T, Failure>>;
}

// Reads from the command line and, on success, replaces the cache. On failure
// the previous cache is kept and returned with the error, so the view never goes
// blank because one refresh failed.
export async function refresh<T>(options: RefreshOptions<T>): Promise<Snapshot<T>> {
  const result = await options.read();
  if (result.ok) {
    const readAt = options.now().toISOString();
    options.cache.save(options.name, { savedAt: readAt, key: options.key, value: result.value });
    return { state: "fresh", value: result.value, readAt };
  }
  const previous = options.cache.load<T>(options.name, options.key);
  if (previous === null) return { state: "unavailable", error: result.error };
  return { state: "stale", value: previous.value, readAt: previous.savedAt, error: result.error };
}
