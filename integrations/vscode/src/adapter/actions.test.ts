import assert from "node:assert/strict";
import { test } from "node:test";
import {
  adoptEntries,
  removeEntry,
  reapplyProject,
  COLLISION_TEXT,
  DRIFT_ABORT_TEXT,
} from "./actions.ts";
import { createCommands } from "./commands.ts";
import type { RunResult } from "./run.ts";
import { sample } from "./support.ts";

function exited(code: number, stdout = "", stderr = ""): RunResult {
  return { kind: "exited", code, stdout, stderr };
}

// A fake command line that records every call and answers by the command asked.
function fake(answer: (args: readonly string[]) => RunResult) {
  const calls: string[][] = [];
  const run = (args: readonly string[]): Promise<RunResult> => {
    calls.push([...args]);
    return Promise.resolve(answer(args));
  };
  return { run, calls };
}

test("remove runs the command with the confirmation flag and the id after a separator", async () => {
  const { run, calls } = fake(() => exited(0, "removed commit-style\n"));
  const outcome = await removeEntry(run, "snippet", "commit-style");
  assert.deepEqual(outcome, { kind: "done", summary: "removed commit-style" });
  assert.deepEqual(calls, [["snippet", "remove", "--yes", "--", "commit-style"]]);
});

test("removing a skill uses the skill command", async () => {
  const { run, calls } = fake(() => exited(0, "removed code-review\n"));
  await removeEntry(run, "skill", "code-review");
  assert.deepEqual(calls[0]?.slice(0, 2), ["skill", "remove"]);
});

test("removing an id that does not exist shows the command line's words", async () => {
  const { run } = fake(() => exited(1, "", "error: no snippet 'nope' in the library"));
  const outcome = await removeEntry(run, "snippet", "nope");
  assert.equal(outcome.kind, "needs-attention");
  if (outcome.kind === "needs-attention") assert.match(outcome.message, /no snippet 'nope'/);
});

test("a remove that cannot run is a failure", async () => {
  const { run } = fake(() => ({ kind: "timeout", timeoutMs: 1000 }));
  const outcome = await removeEntry(run, "snippet", "x");
  assert.equal(outcome.kind, "failed");
});

test("adopt with nothing in the way is done and carries what was adopted", async () => {
  const { run, calls } = fake(() => exited(0, "  adopted: a-new, z-collide\n"));
  const outcome = await adoptEntries(run, "snippet");
  assert.deepEqual(outcome, { kind: "done", summary: "adopted: a-new, z-collide" });
  assert.deepEqual(calls, [["snippet", "adopt"]]);
});

test("a collision stops adopt and is reported as one, so the user can decide", async () => {
  const { run } = fake(() =>
    exited(1, "  library copy of 'x':\n    A\n", `warning: snippet 'x' ${COLLISION_TEXT}\n`),
  );
  const outcome = await adoptEntries(run, "snippet");
  assert.equal(outcome.kind, "collision");
});

test("the user's choice is passed on as the collision flag", async () => {
  const keep = fake(() => exited(0, "  kept the library copy of: x\n"));
  await adoptEntries(keep.run, "skill", "keep");
  assert.deepEqual(keep.calls, [["skill", "adopt", "--on-collision", "keep"]]);
  const overwrite = fake(() => exited(0, "  overwrote: x\n"));
  await adoptEntries(overwrite.run, "snippet", "overwrite");
  assert.deepEqual(overwrite.calls, [["snippet", "adopt", "--on-collision", "overwrite"]]);
});

test("adopt with no manifest is a condition to fix in the command line's words", async () => {
  const { run } = fake(() =>
    exited(1, "", "error: /p has no mdcompose.lock, so there is nothing to adopt"),
  );
  const outcome = await adoptEntries(run, "snippet");
  assert.equal(outcome.kind, "needs-attention");
  if (outcome.kind === "needs-attention") assert.match(outcome.message, /nothing to adopt/);
});

function commandsFor(driftStatus: string, initialized = true) {
  const document = sample("doctor") as Record<string, unknown>;
  const drift = initialized
    ? [
        { file: "agents_md", path: "p", status: driftStatus, detail: null },
        { file: "claude_md", path: "p", status: "clean", detail: null },
      ]
    : null;
  const run = (args: readonly string[]): Promise<RunResult> => {
    if (args.join(" ") === "--json doctor") {
      return Promise.resolve(exited(0, JSON.stringify({ ...document, initialized, drift })));
    }
    throw new Error(`unexpected ${args.join(" ")}`);
  };
  return createCommands(run);
}

test("reapply on a clean project runs init with drift set to abort", async () => {
  const { run, calls } = fake(() => exited(0, "  unchanged: agents_md, claude_md\n"));
  const outcome = await reapplyProject(commandsFor("clean"), run);
  assert.deepEqual(outcome, { kind: "done", summary: "unchanged: agents_md, claude_md" });
  assert.deepEqual(calls, [["init", "--reapply", "--on-drift", "abort"]]);
});

test("reapply finds hand edits from the health report and runs nothing", async () => {
  const { run, calls } = fake(() => exited(0, ""));
  const outcome = await reapplyProject(commandsFor("drifted"), run);
  assert.deepEqual(outcome, { kind: "drift", files: ["agents_md"] });
  assert.deepEqual(calls, []);
});

test("reapply on a project that was never composed says so and runs nothing", async () => {
  const { run, calls } = fake(() => exited(0, ""));
  const outcome = await reapplyProject(commandsFor("clean", false), run);
  assert.deepEqual(outcome, { kind: "not-composed" });
  assert.deepEqual(calls, []);
});

test("if a file drifts between the check and the run, the abort is reported as drift", async () => {
  const { run } = fake(() => exited(1, `${DRIFT_ABORT_TEXT}\n`));
  const outcome = await reapplyProject(commandsFor("clean"), run);
  assert.deepEqual(outcome, { kind: "drift", files: [] });
});

test("other trouble during reapply shows the command line's words", async () => {
  const { run } = fake(() => exited(1, "", "error: cannot use the config file"));
  const outcome = await reapplyProject(commandsFor("clean"), run);
  assert.equal(outcome.kind, "needs-attention");
});

test("a health report that cannot be read fails the reapply before anything runs", async () => {
  const commands = createCommands(() =>
    Promise.resolve<RunResult>({ kind: "timeout", timeoutMs: 1 }),
  );
  const { run, calls } = fake(() => exited(0, ""));
  const outcome = await reapplyProject(commands, run);
  assert.equal(outcome.kind, "failed");
  assert.deepEqual(calls, []);
});
