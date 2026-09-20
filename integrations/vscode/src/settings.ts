// Reading the extension's settings safely. Nothing here touches the editor.

// The shape the editor returns when asked where a setting's value comes from.
export interface Inspected<T> {
  globalValue?: T;
  globalLocalValue?: T;
  globalRemoteValue?: T;
  workspaceValue?: T;
  workspaceFolderValue?: T;
}

// The value the user set for themselves or for the machine, ignoring any value a
// workspace or a folder supplies. A repository can ship workspace settings, and
// letting one name the program the extension runs would let opening a repository
// run arbitrary code. The setting is also declared machine-scoped in the manifest,
// so the editor does not offer it for workspaces; this is the second lock.
export function machineValue<T>(inspected: Inspected<T> | undefined): T | undefined {
  if (inspected === undefined) return undefined;
  return inspected.globalRemoteValue ?? inspected.globalLocalValue ?? inspected.globalValue;
}

export const DEFAULT_TIMEOUT_SECONDS = 30;
const MAX_TIMEOUT_SECONDS = 600;

export function timeoutMilliseconds(seconds: unknown): number {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 1) {
    return DEFAULT_TIMEOUT_SECONDS * 1000;
  }
  return Math.min(seconds, MAX_TIMEOUT_SECONDS) * 1000;
}
