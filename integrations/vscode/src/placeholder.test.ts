import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

// The publisher id is not chosen yet, so it is the placeholder `publisher-tbd`.
// These tests keep it in the few places scripts/set-publisher.mjs replaces, so
// swapping in the real id later cannot miss one.

const root = process.cwd();
const PLACEHOLDER = "publisher-tbd";
const REPLACED_BY_THE_SCRIPT = ["package.json", "DEVELOPMENT.md"];
const MAY_MENTION_IT = [...REPLACED_BY_THE_SCRIPT, join("scripts", "set-publisher.mjs")];

function filesToScan(): string[] {
  const top = readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.(json|md|mjs|ts)$/.test(entry.name))
    .filter((entry) => entry.name !== "package-lock.json")
    .map((entry) => entry.name);
  const scripts = readdirSync(join(root, "scripts")).map((name) => join("scripts", name));
  return [...top, ...scripts];
}

test("the publisher id is either the placeholder or a valid id", () => {
  const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
    publisher: string;
  };
  // Lower-case letters, digits, and hyphens satisfy both registries.
  assert.match(manifest.publisher, /^[a-z0-9][a-z0-9-]*$/);
});

test("the placeholder appears only in files the replace script covers", () => {
  for (const file of filesToScan()) {
    if (MAY_MENTION_IT.includes(file)) continue;
    const text = readFileSync(join(root, file), "utf8");
    assert.ok(!text.includes(PLACEHOLDER), `${file} mentions ${PLACEHOLDER}`);
  }
});

test("the replace script covers every file that names the placeholder", () => {
  const script = readFileSync(join(root, "scripts", "set-publisher.mjs"), "utf8");
  for (const file of REPLACED_BY_THE_SCRIPT) {
    assert.ok(script.includes(`"${file}"`), `${file} is not in the script's list`);
  }
});
