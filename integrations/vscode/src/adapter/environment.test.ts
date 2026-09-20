import assert from "node:assert/strict";
import { test } from "node:test";
import { HIGHEST_TESTED_CLI_VERSION, MINIMUM_CLI_VERSION } from "./compat.ts";
import { resolveEnvironment, type EnvironmentDeps } from "./environment.ts";
import type { Inspection } from "./locate.ts";
import type { RunResult } from "./run.ts";

function deps(overrides: Partial<EnvironmentDeps> = {}): EnvironmentDeps {
  return {
    setting: undefined,
    env: { PATH: "/usr/local/bin" },
    platform: "linux",
    inspect: (path: string): Inspection => (path === "/usr/local/bin/mdcompose" ? "ok" : "missing"),
    runVersion: () => Promise.resolve(exited(0, `${MINIMUM_CLI_VERSION}\n`)),
    ...overrides,
  };
}

function exited(code: number, stdout: string, stderr = ""): RunResult {
  return { kind: "exited", code, stdout, stderr };
}

test("a suitable command line on the search path is ready", async () => {
  const environment = await resolveEnvironment(deps());
  assert.deepEqual(environment, {
    kind: "ready",
    executable: "/usr/local/bin/mdcompose",
    version: MINIMUM_CLI_VERSION,
    newerThanTested: false,
  });
});

test("nothing found is reported as not found, naming both places", async () => {
  const environment = await resolveEnvironment(deps({ inspect: () => "missing" }));
  assert.equal(environment.kind, "not-found");
  assert.match(environment.kind === "not-found" ? environment.message : "", /setting.*search path/);
});

test("a setting that cannot be used is reported without trying the search path", async () => {
  const environment = await resolveEnvironment(
    deps({ setting: "/typo/mdcompose", inspect: () => "missing" }),
  );
  assert.equal(environment.kind, "setting-unusable");
  assert.match(
    environment.kind === "setting-unusable" ? environment.message : "",
    /\/typo\/mdcompose/,
  );
});

test("a command line below the minimum is too old and says which versions", async () => {
  const environment = await resolveEnvironment(
    deps({ runVersion: () => Promise.resolve(exited(0, "0.2.0\n")) }),
  );
  assert.equal(environment.kind, "too-old");
  if (environment.kind !== "too-old") return;
  assert.equal(environment.installed, "0.2.0");
  assert.equal(environment.minimum, MINIMUM_CLI_VERSION);
  assert.match(environment.message, /older than the/);
});

test("a command line above the highest tested still runs, flagged as newer", async () => {
  const environment = await resolveEnvironment(
    deps({ runVersion: () => Promise.resolve(exited(0, "9.0.0\n")) }),
  );
  assert.equal(environment.kind, "ready");
  if (environment.kind === "ready") assert.equal(environment.newerThanTested, true);
  assert.ok(HIGHEST_TESTED_CLI_VERSION.length > 0);
});

test("a version output that is not a version is unreadable", async () => {
  const environment = await resolveEnvironment(
    deps({ runVersion: () => Promise.resolve(exited(0, "hello")) }),
  );
  assert.equal(environment.kind, "unreadable");
  assert.match(environment.kind === "unreadable" ? environment.message : "", /hello/);
});

test("a version run that fails is unreadable and carries the failure", async () => {
  const environment = await resolveEnvironment(
    deps({ runVersion: () => Promise.resolve<RunResult>({ kind: "timeout", timeoutMs: 5000 }) }),
  );
  assert.equal(environment.kind, "unreadable");
  assert.match(environment.kind === "unreadable" ? environment.message : "", /did not finish/);
});
