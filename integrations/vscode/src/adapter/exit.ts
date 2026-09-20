import { fail, ok, type Failure, type Result } from "./result.ts";
import type { RunResult } from "./run.ts";

// The command line's exit codes: 0 healthy, 1 the user or environment needs to
// act, 2 mdcompose itself failed. A report command that finds a condition exits 1
// and still prints its complete document, so exit 1 is not always a failure.
export interface Finished {
  code: 0 | 1;
  stdout: string;
  stderr: string;
}

function words(run: { stdout: string; stderr: string }): string {
  const text = run.stderr.trim() !== "" ? run.stderr : run.stdout;
  return text.trim();
}

// Sorts a finished run into success, attention (exit 1), or a failure. A caller
// that expects a document reads it from `Finished` even when the code is 1.
export function mapRun(run: RunResult): Result<Finished, Failure> {
  switch (run.kind) {
    case "timeout":
      return fail({
        kind: "timeout",
        message: `mdcompose did not finish within ${run.timeoutMs / 1000} seconds and was stopped.`,
      });
    case "output-too-large":
      return fail({
        kind: "output-too-large",
        message: `mdcompose printed more than ${run.limit} bytes, so the output was discarded.`,
      });
    case "signalled":
      return fail({
        kind: "unexpected-exit",
        code: -1,
        message: `mdcompose was ended by the signal ${run.signal}.`,
      });
    case "spawn-failed":
      return fail({
        kind: "spawn-failed",
        message: `mdcompose could not be started: ${run.message}`,
      });
    case "exited":
      break;
  }
  if (run.code === 0 || run.code === 1) {
    return ok({ code: run.code, stdout: run.stdout, stderr: run.stderr });
  }
  if (run.code === 2) {
    return fail({
      kind: "mdcompose-failed",
      message: `mdcompose failed, which is a bug in mdcompose: ${words(run)}`,
    });
  }
  return fail({
    kind: "unexpected-exit",
    code: run.code,
    message: `mdcompose exited with the unexpected code ${run.code}: ${words(run)}`,
  });
}

// The message for a command that exited 1 without printing a document: the
// command line's own words, presented as something to fix.
export function attentionMessage(finished: Finished): string {
  const text = words(finished);
  return text === "" ? "mdcompose reported a condition to resolve." : text;
}

// A report command's result: the parsed document plus whether the command line
// flagged a condition (exit 1). Exit 1 without a document is a failure to fix.
export interface Document {
  value: unknown;
  attention: boolean;
}

export function readDocument(run: RunResult): Result<Document, Failure> {
  const mapped = mapRun(run);
  if (!mapped.ok) return mapped;
  const finished = mapped.value;
  let value: unknown;
  try {
    value = JSON.parse(finished.stdout);
  } catch {
    if (finished.code === 1) {
      return fail({ kind: "needs-attention", message: attentionMessage(finished) });
    }
    return fail({
      kind: "not-json",
      message: `mdcompose did not print a single JSON document. ${words(finished)}`.trim(),
    });
  }
  return ok({ value, attention: finished.code === 1 });
}
