import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_TIMEOUT_SECONDS, machineValue, timeoutMilliseconds } from "./settings.ts";

test("a user setting is used", () => {
  assert.equal(machineValue({ globalValue: "/user/mdcompose" }), "/user/mdcompose");
});

test("a remote machine setting wins over a local one", () => {
  assert.equal(
    machineValue({ globalLocalValue: "/local", globalRemoteValue: "/remote" }),
    "/remote",
  );
});

test("a value from a workspace or a folder is ignored", () => {
  assert.equal(
    machineValue({ workspaceValue: "/evil/mdcompose", workspaceFolderValue: "/evil2" }),
    undefined,
  );
  assert.equal(
    machineValue({ globalValue: "/user/mdcompose", workspaceValue: "/evil/mdcompose" }),
    "/user/mdcompose",
  );
});

test("no inspection means no value", () => {
  assert.equal(machineValue(undefined), undefined);
});

test("the timeout falls back to the default for anything unusable", () => {
  const fallback = DEFAULT_TIMEOUT_SECONDS * 1000;
  assert.equal(timeoutMilliseconds(undefined), fallback);
  assert.equal(timeoutMilliseconds("10"), fallback);
  assert.equal(timeoutMilliseconds(0), fallback);
  assert.equal(timeoutMilliseconds(Number.NaN), fallback);
});

test("a sensible timeout is used and a huge one is capped", () => {
  assert.equal(timeoutMilliseconds(5), 5000);
  assert.equal(timeoutMilliseconds(100000), 600_000);
});
