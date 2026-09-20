import assert from "node:assert/strict";
import { test } from "node:test";
import { attentionMessage, mapRun, readDocument } from "./exit.ts";
import type { RunResult } from "./run.ts";

function exited(code: number, stdout = "", stderr = ""): RunResult {
  return { kind: "exited", code, stdout, stderr };
}

test("exit code 0 is success", () => {
  const result = mapRun(exited(0, "ok"));
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.value.code, 0);
});

test("exit code 1 is a condition to fix, carried as a finished run", () => {
  const result = mapRun(exited(1, "", "error: no snippet 'x' in the library"));
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.code, 1);
  assert.match(attentionMessage(result.value), /no snippet 'x'/);
});

test("exit code 2 is an mdcompose failure, described as one", () => {
  const result = mapRun(exited(2, "", "Traceback"));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.kind, "mdcompose-failed");
  assert.match(result.error.message, /bug in mdcompose/);
});

test("any other exit code is unexpected and carries the code and the error output", () => {
  const result = mapRun(exited(137, "", "killed"));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.kind, "unexpected-exit");
  if (result.error.kind === "unexpected-exit") assert.equal(result.error.code, 137);
  assert.match(result.error.message, /137/);
  assert.match(result.error.message, /killed/);
});

test("a timeout, a signal, and a failure to start are each their own failure", () => {
  const timeout = mapRun({ kind: "timeout", timeoutMs: 30_000 });
  const signalled = mapRun({ kind: "signalled", signal: "SIGTERM" });
  const spawnFailed = mapRun({ kind: "spawn-failed", message: "ENOENT" });
  const tooLarge = mapRun({ kind: "output-too-large", limit: 10 });
  const kinds = [timeout, signalled, spawnFailed, tooLarge].map((r) =>
    r.ok ? "ok" : r.error.kind,
  );
  assert.deepEqual(kinds, ["timeout", "unexpected-exit", "spawn-failed", "output-too-large"]);
});

test("a report that exits 1 with a document is read, and flagged", () => {
  const result = readDocument(exited(1, '{"os":"linux"}'));
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.attention, true);
  assert.deepEqual(result.value.value, { os: "linux" });
});

test("a report that exits 0 with a document is read without a flag", () => {
  const result = readDocument(exited(0, '{"os":"linux"}'));
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.value.attention, false);
});

test("exit 1 without a document is a condition to fix, in the command line's words", () => {
  const result = readDocument(exited(1, "", "error: cannot use the config file"));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.kind, "needs-attention");
  assert.match(result.error.message, /cannot use the config file/);
});

test("exit 0 with output that is not JSON is a failure and shows the error output", () => {
  const result = readDocument(exited(0, "not json", "warning: something"));
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.kind, "not-json");
  assert.match(result.error.message, /warning: something/);
});

test("output that is only part of a document is not repaired", () => {
  const result = readDocument(exited(0, '{"os": "linux"'));
  assert.equal(result.ok, false);
  if (!result.ok) assert.equal(result.error.kind, "not-json");
});

test("a failure to run passes through untouched", () => {
  const result = readDocument({ kind: "timeout", timeoutMs: 1000 });
  assert.equal(result.ok, false);
  if (!result.ok) assert.equal(result.error.kind, "timeout");
});
