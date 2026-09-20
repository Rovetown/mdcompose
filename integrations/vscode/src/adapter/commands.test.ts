import assert from "node:assert/strict";
import { test } from "node:test";
import { createCommands } from "./commands.ts";
import type { RunResult } from "./run.ts";
import { sample } from "./support.ts";

// The fake `run` answers by the command asked for and records what it was given.
function fakeRun(answers: Record<string, RunResult>) {
  const calls: string[][] = [];
  const run = (args: readonly string[]): Promise<RunResult> => {
    calls.push([...args]);
    const answer = answers[args.join(" ")];
    if (answer === undefined) throw new Error(`unexpected command: ${args.join(" ")}`);
    return Promise.resolve(answer);
  };
  return { run, calls };
}

function json(value: unknown, code = 0): RunResult {
  return { kind: "exited", code, stdout: JSON.stringify(value), stderr: "" };
}

test("each list runs its command with the JSON option before it", async () => {
  const { run, calls } = fakeRun({
    "--json snippet list": json(sample("snippet-list")),
    "--json skill list": json(sample("skill-list")),
  });
  const commands = createCommands(run);
  const snippets = await commands.snippetList();
  const skills = await commands.skillList();
  assert.equal(snippets.ok && snippets.value.entries.length, 2);
  assert.equal(skills.ok && skills.value.entries.length, 1);
  assert.deepEqual(calls, [
    ["--json", "snippet", "list"],
    ["--json", "skill", "list"],
  ]);
});

test("a healthy project reads without a flag", async () => {
  const { run } = fakeRun({ "--json doctor": json(sample("doctor"), 0) });
  const health = await createCommands(run).health();
  assert.equal(health.ok, true);
  if (health.ok) assert.equal(health.value.attention, false);
});

test("a report that found a condition is read, flagged, and keeps its document", async () => {
  const { run } = fakeRun({ "--json doctor": json(sample("doctor"), 1) });
  const health = await createCommands(run).health();
  assert.equal(health.ok, true);
  if (!health.ok) return;
  assert.equal(health.value.attention, true);
  assert.equal(health.value.report.targets[0]?.sync, "missing");
});

test("exit 1 without a document is a failure carrying the command line's words", async () => {
  const { run } = fakeRun({
    "--json doctor": { kind: "exited", code: 1, stdout: "", stderr: "error: bad config" },
  });
  const health = await createCommands(run).health();
  assert.equal(health.ok, false);
  if (!health.ok) assert.match(health.error.message, /bad config/);
});

test("a report missing a needed field is an incompatible version, not a crash", async () => {
  const { run } = fakeRun({ "--json snippet list": json({ library: "/x" }) });
  const snippets = await createCommands(run).snippetList();
  assert.equal(snippets.ok, false);
  if (!snippets.ok) assert.equal(snippets.error.kind, "incompatible");
});

test("a failure to run passes through", async () => {
  const { run } = fakeRun({ "--json skill list": { kind: "timeout", timeoutMs: 1000 } });
  const skills = await createCommands(run).skillList();
  assert.equal(skills.ok, false);
  if (!skills.ok) assert.equal(skills.error.kind, "timeout");
});
