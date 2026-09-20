import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { runCommand, type RunResult } from "./run.ts";
import { scratch } from "./support.ts";

// The fake command line is a small Node script started through the Node
// executable, so no shell and no launcher file is involved on any platform.
const FAKE = `
const [, , mode, ...rest] = process.argv;
if (mode === "echo") {
  process.stdout.write(JSON.stringify({ args: rest, cwd: process.cwd() }));
} else if (mode === "exit") {
  process.stdout.write("out");
  process.stderr.write("boom");
  process.exit(Number(rest[0]));
} else if (mode === "sleep") {
  require("node:fs").writeFileSync(rest[0], String(process.pid));
  setTimeout(() => {}, 60000);
} else if (mode === "flood") {
  process.stdout.write("x".repeat(Number(rest[0])));
} else if (mode === "stdin") {
  process.stdin.on("end", () => process.stdout.write("stdin-closed"));
  process.stdin.resume();
}
`;

function setup() {
  const { dir, cleanup } = scratch();
  const script = join(dir, "fake.js");
  writeFileSync(script, FAKE);
  return { dir, script, cleanup };
}

function exited(result: RunResult) {
  assert.equal(result.kind, "exited", JSON.stringify(result));
  if (result.kind !== "exited") throw new Error("unreachable");
  return result;
}

test("arguments reach the program exactly as given, with no shell in between", async () => {
  const { dir, script, cleanup } = setup();
  try {
    const args = ["a b", 'c"d', "e'f", "g&h", "i|j", "$HOME", "`x`", "%PATH%", "k;l", "(m)"];
    const result = exited(
      await runCommand({
        executable: process.execPath,
        args: [script, "echo", ...args],
        cwd: dir,
        timeoutMs: 10_000,
      }),
    );
    const parsed = JSON.parse(result.stdout) as { args: string[] };
    assert.deepEqual(parsed.args, args);
    assert.equal(result.code, 0);
  } finally {
    cleanup();
  }
});

test("the working directory may contain spaces, quotes, and parentheses", async () => {
  const { dir, script, cleanup } = setup();
  try {
    const cwd = join(dir, "my project (v2) 'x'");
    mkdirSync(cwd);
    const result = exited(
      await runCommand({
        executable: process.execPath,
        args: [script, "echo"],
        cwd,
        timeoutMs: 10_000,
      }),
    );
    const parsed = JSON.parse(result.stdout) as { cwd: string };
    assert.equal(parsed.cwd.toLowerCase(), cwd.toLowerCase());
  } finally {
    cleanup();
  }
});

test("the exit code and both output streams are returned", async () => {
  const { dir, script, cleanup } = setup();
  try {
    const result = exited(
      await runCommand({
        executable: process.execPath,
        args: [script, "exit", "3"],
        cwd: dir,
        timeoutMs: 10_000,
      }),
    );
    assert.equal(result.code, 3);
    assert.equal(result.stdout, "out");
    assert.equal(result.stderr, "boom");
  } finally {
    cleanup();
  }
});

test("standard input is closed, so a program waiting for input ends at once", async () => {
  const { dir, script, cleanup } = setup();
  try {
    const result = exited(
      await runCommand({
        executable: process.execPath,
        args: [script, "stdin"],
        cwd: dir,
        timeoutMs: 10_000,
      }),
    );
    assert.equal(result.stdout, "stdin-closed");
  } finally {
    cleanup();
  }
});

test("a command that runs too long is stopped and reported, and does not keep running", async () => {
  const { dir, script, cleanup } = setup();
  try {
    const pidFile = join(dir, "pid.txt");
    const started = Date.now();
    const result = await runCommand({
      executable: process.execPath,
      args: [script, "sleep", pidFile],
      cwd: dir,
      timeoutMs: 1500,
    });
    assert.equal(result.kind, "timeout");
    assert.ok(Date.now() - started < 15_000);
    assert.ok(existsSync(pidFile), "the fake program started");
    const pid = Number(readFileSync(pidFile, "utf8"));
    await new Promise((resolve) => setTimeout(resolve, 500));
    let alive = true;
    try {
      process.kill(pid, 0);
    } catch {
      alive = false;
    }
    assert.equal(alive, false, "the timed-out process is gone");
  } finally {
    cleanup();
  }
});

test("output beyond the limit is refused", async () => {
  const { script, cleanup } = setup();
  try {
    const result = await runCommand({
      executable: process.execPath,
      args: [script, "flood", "100000"],
      // Not the scratch directory: on Windows a process still shutting down would
      // hold it as its working directory and block its removal.
      cwd: tmpdir(),
      timeoutMs: 10_000,
      maxOutputBytes: 1000,
    });
    assert.equal(result.kind, "output-too-large");
  } finally {
    cleanup();
  }
});

test("a program that does not exist is a failure to start, not an exit code", async () => {
  const { dir, cleanup } = setup();
  try {
    const result = await runCommand({
      executable: join(dir, "no-such-program"),
      args: [],
      cwd: dir,
      timeoutMs: 10_000,
    });
    assert.equal(result.kind, "spawn-failed");
  } finally {
    cleanup();
  }
});
