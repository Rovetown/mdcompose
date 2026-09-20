import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

// The extension makes no network request of its own and sends no telemetry. These
// tests scan what ships, the sources and the bundle, for anything that could, so a
// change that adds one fails here and has to be a deliberate decision.

const root = process.cwd();

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    const shipped = entry.name.endsWith(".ts") && !entry.name.endsWith(".test.ts");
    return shipped && entry.name !== "support.ts" ? [path] : [];
  });
}

// Ways to reach the network or report usage, written as pieces so this file does
// not match its own patterns.
const NETWORK = [
  "node:" + "http",
  "node:" + "https",
  "node:" + "http2",
  "node:" + "net",
  "node:" + "tls",
  "node:" + "dgram",
  "node:" + "dns",
  "fetch" + "(",
  "Web" + "Socket",
  "XMLHttp" + "Request",
  "undici",
  "axios",
];
const TELEMETRY = ["createTelemetry" + "Logger", "extension-" + "telemetry", "applicationinsights"];

test("no shipped source can reach the network or report telemetry", () => {
  for (const file of sourceFiles(join(root, "src"))) {
    const text = readFileSync(file, "utf8");
    for (const pattern of [...NETWORK, ...TELEMETRY]) {
      assert.ok(!text.includes(pattern), `${file} contains ${pattern}`);
    }
  }
});

test("the built bundle holds no network or telemetry code", () => {
  const bundle = join(root, "dist", "extension.js");
  if (!existsSync(bundle)) return;
  const text = readFileSync(bundle, "utf8");
  for (const pattern of [...NETWORK, ...TELEMETRY]) {
    assert.ok(!text.includes(pattern), `the bundle contains ${pattern}`);
  }
});

test("the extension ships no runtime dependency, so nothing but its own code is bundled", () => {
  const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
    dependencies?: Record<string, string>;
  };
  assert.deepEqual(Object.keys(manifest.dependencies ?? {}), []);
});

test("only the runner starts a program, and it never uses a shell", () => {
  const starters = sourceFiles(join(root, "src")).filter((file) =>
    /child_process/.test(readFileSync(file, "utf8")),
  );
  assert.deepEqual(
    starters.map((file) => file.slice(root.length + 1).replaceAll("\\", "/")),
    ["src/adapter/run.ts"],
  );
  const runner = readFileSync(join(root, "src", "adapter", "run.ts"), "utf8");
  assert.match(runner, /shell: false/);
  assert.match(runner, /windowsHide: true/);
});
