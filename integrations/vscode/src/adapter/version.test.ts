import assert from "node:assert/strict";
import { test } from "node:test";
import { HIGHEST_TESTED_CLI_VERSION, MINIMUM_CLI_VERSION } from "./compat.ts";
import { checkCompatibility, compareVersions, parseVersion } from "./version.ts";

function must(text: string) {
  const version = parseVersion(text);
  assert.ok(version, `${text} should parse`);
  return version;
}

test("versions parse with a leading v, whitespace, and a pre-release suffix", () => {
  assert.deepEqual(must("0.3.0"), { release: [0, 3, 0], preRelease: false });
  assert.deepEqual(must("  v1.2 \n"), { release: [1, 2], preRelease: false });
  assert.deepEqual(must("0.4.0a1"), { release: [0, 4, 0], preRelease: true });
  assert.deepEqual(must("1.0.0.dev3"), { release: [1, 0, 0], preRelease: true });
});

test("text that is not a version does not parse", () => {
  assert.equal(parseVersion("mdcompose"), null);
  assert.equal(parseVersion(""), null);
});

test("versions compare by release number, and a pre-release sorts just below its release", () => {
  assert.ok(compareVersions(must("0.3.1"), must("0.3.0")) > 0);
  assert.ok(compareVersions(must("0.10.0"), must("0.9.0")) > 0);
  assert.equal(compareVersions(must("1.0"), must("1.0.0")), 0);
  assert.ok(compareVersions(must("0.4.0a1"), must("0.4.0")) < 0);
  assert.ok(compareVersions(must("0.4.0a1"), must("0.3.9")) > 0);
});

test("a command line below the minimum is too old", () => {
  const result = checkCompatibility("0.2.9\n", "0.3.0", "0.3.0");
  assert.deepEqual(result, { kind: "too-old", installed: "0.2.9", minimum: "0.3.0" });
});

test("a command line inside the tested range is fine", () => {
  assert.deepEqual(checkCompatibility("0.3.0", "0.3.0", "0.3.4"), { kind: "ok" });
  assert.deepEqual(checkCompatibility("0.3.4", "0.3.0", "0.3.4"), { kind: "ok" });
});

test("a command line above the highest tested is newer than tested", () => {
  const result = checkCompatibility("0.4.0", "0.3.0", "0.3.4");
  assert.deepEqual(result, {
    kind: "newer-than-tested",
    installed: "0.4.0",
    highestTested: "0.3.4",
  });
});

test("output that is not a version is unreadable", () => {
  const result = checkCompatibility("garbled", "0.3.0", "0.3.0");
  assert.deepEqual(result, { kind: "unreadable", output: "garbled" });
});

test("the declared range is well formed and ordered", () => {
  const lowest = must(MINIMUM_CLI_VERSION);
  const highest = must(HIGHEST_TESTED_CLI_VERSION);
  assert.ok(compareVersions(lowest, highest) <= 0);
});
