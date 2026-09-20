import type { Commands } from "./commands.ts";
import { attentionMessage, mapRun } from "./exit.ts";
import type { Failure } from "./result.ts";
import type { RunResult } from "./run.ts";

// The actions that change something, each a command the command line already has.
// They take the command runner as a parameter, so the rules (which flags, which
// exit code means what) are tested without an editor or a real command line.

export type Run = (args: readonly string[]) => Promise<RunResult>;
export type LibraryKind = "snippet" | "skill";

// Words the command line prints that this code reacts to. They are kept here, in
// one place, because a change to them in the command line would change behavior
// here. tests/test_integration_contract.py in the main suite checks the same
// wording against the real command line.
export const COLLISION_TEXT = "already exists in the library with different content";
export const DRIFT_ABORT_TEXT = "aborted, nothing written";

export type ActionOutcome =
  | { kind: "done"; summary: string }
  | { kind: "needs-attention"; message: string }
  | { kind: "failed"; failure: Failure };

export type CollisionChoice = "keep" | "overwrite";

export type AdoptOutcome = ActionOutcome | { kind: "collision"; message: string };

export type ReapplyOutcome =
  | ActionOutcome
  | { kind: "not-composed" }
  // Managed files edited by hand since mdcompose wrote them: nothing was changed.
  | { kind: "drift"; files: string[] };

// What the command line printed, on one line, for showing to the user.
function summarise(text: string): string {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "")
    .join("; ");
}

export async function removeEntry(run: Run, kind: LibraryKind, id: string): Promise<ActionOutcome> {
  // "--" keeps an id that starts with a dash from being read as an option.
  const result = mapRun(await run([kind, "remove", "--yes", "--", id]));
  if (!result.ok) return { kind: "failed", failure: result.error };
  if (result.value.code === 1) {
    return { kind: "needs-attention", message: attentionMessage(result.value) };
  }
  return { kind: "done", summary: summarise(result.value.stdout) };
}

// Adopts the entries embedded in the project's manifest. Without a choice, a
// collision with a different library copy stops everything and writes nothing, so
// the caller can ask the user and run it again with their answer.
export async function adoptEntries(
  run: Run,
  kind: LibraryKind,
  choice?: CollisionChoice,
): Promise<AdoptOutcome> {
  const args = [kind, "adopt", ...(choice === undefined ? [] : ["--on-collision", choice])];
  const result = mapRun(await run(args));
  if (!result.ok) return { kind: "failed", failure: result.error };
  if (result.value.code === 1) {
    const text = `${result.value.stderr}\n${result.value.stdout}`;
    if (text.includes(COLLISION_TEXT)) {
      return {
        kind: "collision",
        message: "Some entries already exist in your library with different content.",
      };
    }
    return { kind: "needs-attention", message: attentionMessage(result.value) };
  }
  return { kind: "done", summary: summarise(result.value.stdout) };
}

// Re-composes the project from its recorded selection, never overwriting hand
// edits. It reads the health report first, so drift is found from documented
// fields and not from wording; the run itself is told to abort on drift as a
// second guard against a file changing in between.
export async function reapplyProject(commands: Commands, run: Run): Promise<ReapplyOutcome> {
  const health = await commands.health();
  if (!health.ok) return { kind: "failed", failure: health.error };
  const drift = health.value.report.drift;
  if (drift === null) return { kind: "not-composed" };
  const drifted = drift.filter((entry) => entry.status !== "clean").map((entry) => entry.file);
  if (drifted.length > 0) return { kind: "drift", files: drifted };

  const result = mapRun(await run(["init", "--reapply", "--on-drift", "abort"]));
  if (!result.ok) return { kind: "failed", failure: result.error };
  if (result.value.code === 1) {
    const text = `${result.value.stdout}\n${result.value.stderr}`;
    if (text.includes(DRIFT_ABORT_TEXT)) return { kind: "drift", files: [] };
    return { kind: "needs-attention", message: attentionMessage(result.value) };
  }
  return { kind: "done", summary: summarise(result.value.stdout) };
}
