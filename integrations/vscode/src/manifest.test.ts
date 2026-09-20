import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

// These tests guard the rules that keep the toolchain swappable and the package
// installable. They read the manifest and the sources, never the editor.

interface Manifest {
  main: string;
  engines: { vscode: string };
  scripts: Record<string, string>;
  devDependencies: Record<string, string>;
}

// Scripts run from the package root, so the working directory is the root. Node reads
// this file as an ES module, where __dirname does not exist.
const root = process.cwd();
const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as Manifest;

function versionParts(range: string): number[] {
  return range
    .replace(/^[^\d]*/, "")
    .split(".")
    .map(Number);
}

function compare(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const difference = (a[i] ?? 0) - (b[i] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.name.endsWith(".ts") ? [path] : [];
  });
}

test("the editor API types are not newer than the minimum supported editor", () => {
  // The packaging tool refuses to package when the types version exceeds the engine.
  const types = versionParts(manifest.devDependencies["@types/vscode"] ?? "");
  const floor = versionParts(manifest.engines.vscode);
  assert.ok(
    compare(types, floor) <= 0,
    `types ${types.join(".")} exceed engine ${floor.join(".")}`,
  );
});

test("main points at the file the build script writes", () => {
  assert.equal(manifest.main, "./dist/extension.js");
  assert.match(manifest.scripts["build"] ?? "", /--outfile=dist\/extension\.js/);
});

test("no package script depends on a tool only Bun provides", () => {
  // npm is the toolchain of record. Scripts stay free of Bun so that npm, CI, and
  // anyone who prefers to run them with `bun run` all work the same.
  for (const [name, command] of Object.entries(manifest.scripts)) {
    assert.doesNotMatch(command, /\bbun(x)?\b/, `script "${name}" needs Bun`);
  }
});

test("no source file uses a Bun-only API", () => {
  const forbidden = [new RegExp("\\bBun\\."), new RegExp("from [\"']bun:")];
  for (const file of sourceFiles(join(root, "src"))) {
    if (file.endsWith("manifest.test.ts")) continue;
    const text = readFileSync(file, "utf8");
    for (const pattern of forbidden) {
      assert.doesNotMatch(text, pattern, `${file} uses a Bun-only API`);
    }
  }
});

test("the one committed lockfile is package-lock.json", () => {
  // Checked against what git tracks, so a lockfile a tool leaves in the working
  // tree (Bun writes bun.lock if someone runs bun install) does not fail a local run.
  // It is ignored by git, so it can never be committed by accident.
  const names = ["package-lock.json", "bun.lock", "bun.lockb", "yarn.lock", "pnpm-lock.yaml"];
  let tracked: string[];
  try {
    tracked = execFileSync("git", ["ls-files", "--", ...names], { cwd: root, encoding: "utf8" })
      .split("\n")
      .filter((name) => name !== "");
  } catch {
    // Not a git checkout, so fall back to the files on disk.
    tracked = names.filter((name) => existsSync(join(root, name)));
  }
  assert.deepEqual(tracked, ["package-lock.json"]);
});
