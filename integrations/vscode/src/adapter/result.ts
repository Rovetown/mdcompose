// A value or a failure, without exceptions for control flow. Every adapter
// function that can fail for a reason the user should see returns one of these.

export type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

export function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

export function fail<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

// Why a command did not produce a usable answer. `message` is written for the
// user and carries the command line's own words where it has any.
export type Failure =
  | { kind: "needs-attention"; message: string }
  | { kind: "mdcompose-failed"; message: string }
  | { kind: "unexpected-exit"; code: number; message: string }
  | { kind: "timeout"; message: string }
  | { kind: "spawn-failed"; message: string }
  | { kind: "output-too-large"; message: string }
  | { kind: "not-json"; message: string }
  | { kind: "incompatible"; missing: string[]; message: string };
