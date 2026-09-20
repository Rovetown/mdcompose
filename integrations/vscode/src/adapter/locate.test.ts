import assert from "node:assert/strict";
import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import { join, win32 } from "node:path";
import { test } from "node:test";
import {
  describeLocateFailure,
  inspectPath,
  locateExecutable,
  searchDirectories,
  type Inspection,
} from "./locate.ts";
import { scratch } from "./support.ts";

// A fake filesystem: only the listed paths exist, and each is runnable.
function fake(runnable: string[], others: Record<string, Inspection> = {}) {
  return (path: string): Inspection => others[path] ?? (runnable.includes(path) ? "ok" : "missing");
}

const posixEnv = { PATH: "/opt/tools:/usr/local/bin" };

test("an explicit setting is used without looking at the search path", () => {
  let searched = false;
  const inspect = (path: string): Inspection => {
    if (path !== "/custom/mdcompose") searched = true;
    return "ok";
  };
  const located = locateExecutable({
    setting: "/custom/mdcompose",
    env: posixEnv,
    platform: "linux",
    inspect,
  });
  assert.deepEqual(located, { kind: "found", path: "/custom/mdcompose", source: "setting" });
  assert.equal(searched, false);
});

test("the search path is used when no setting is given", () => {
  const located = locateExecutable({
    setting: undefined,
    env: posixEnv,
    platform: "linux",
    inspect: fake(["/usr/local/bin/mdcompose"]),
  });
  assert.deepEqual(located, {
    kind: "found",
    path: "/usr/local/bin/mdcompose",
    source: "search-path",
  });
});

test("an empty setting counts as not set", () => {
  const located = locateExecutable({
    setting: "   ",
    env: posixEnv,
    platform: "linux",
    inspect: fake(["/opt/tools/mdcompose"]),
  });
  assert.equal(located.kind, "found");
});

test("nothing found names both places that were checked", () => {
  const located = locateExecutable({
    setting: undefined,
    env: posixEnv,
    platform: "linux",
    inspect: fake([]),
  });
  assert.equal(located.kind, "not-found");
  if (located.kind !== "not-found") return;
  assert.deepEqual(located.checked.searchDirectories, ["/opt/tools", "/usr/local/bin"]);
  const message = describeLocateFailure(located);
  assert.match(message, /mdcompose\.executablePath setting/);
  assert.match(message, /executable search path \(2 directories\)/);
});

test("a setting that does not run is reported and does not fall back to the search path", () => {
  const located = locateExecutable({
    setting: "/nowhere/mdcompose",
    env: posixEnv,
    platform: "linux",
    inspect: fake(["/usr/local/bin/mdcompose"]),
  });
  assert.equal(located.kind, "setting-unusable");
  if (located.kind !== "setting-unusable") return;
  assert.equal(located.path, "/nowhere/mdcompose");
  assert.match(describeLocateFailure(located), /\/nowhere\/mdcompose.*does not exist/);
});

test("a setting that exists but cannot run says so", () => {
  const located = locateExecutable({
    setting: "/notes.txt",
    env: posixEnv,
    platform: "linux",
    inspect: fake([], { "/notes.txt": "not-executable" }),
  });
  assert.equal(located.kind, "setting-unusable");
  if (located.kind !== "setting-unusable") return;
  assert.match(located.reason, /cannot be run/);
});

test("Windows looks for .exe launchers and ignores .cmd shims", () => {
  const env = { Path: "C:\\Tools;C:\\Other" };
  const withShim = locateExecutable({
    setting: undefined,
    env,
    platform: "win32",
    inspect: fake([win32.join("C:\\Tools", "mdcompose.cmd")]),
  });
  assert.equal(withShim.kind, "not-found");
  const withExe = locateExecutable({
    setting: undefined,
    env,
    platform: "win32",
    inspect: fake([win32.join("C:\\Other", "mdcompose.exe")]),
  });
  assert.equal(withExe.kind, "found");
});

test("the search path variable is found whatever its capitalisation and quoting", () => {
  assert.deepEqual(searchDirectories({ PATH: '"C:\\A B";C:\\C;;' }, "win32"), ["C:\\A B", "C:\\C"]);
  assert.deepEqual(searchDirectories({ pAtH: "/a:/b" }, "linux"), ["/a", "/b"]);
  assert.deepEqual(searchDirectories({}, "linux"), []);
});

test("the real filesystem check tells missing, directory, and file apart", () => {
  const { dir, cleanup } = scratch();
  try {
    assert.equal(inspectPath(join(dir, "absent")), "missing");
    const subdirectory = join(dir, "sub");
    mkdirSync(subdirectory);
    assert.equal(inspectPath(subdirectory), "not-a-file");

    const program = join(dir, process.platform === "win32" ? "mdcompose.exe" : "mdcompose");
    writeFileSync(program, "");
    if (process.platform !== "win32") {
      chmodSync(program, 0o644);
      assert.equal(inspectPath(program), "not-executable");
      chmodSync(program, 0o755);
    }
    assert.equal(inspectPath(program), "ok");

    if (process.platform === "win32") {
      const shim = join(dir, "mdcompose.cmd");
      writeFileSync(shim, "");
      assert.equal(inspectPath(shim), "not-executable");
    }
  } finally {
    cleanup();
  }
});
