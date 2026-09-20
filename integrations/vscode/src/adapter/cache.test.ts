import assert from "node:assert/strict";
import { existsSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { Cache, cacheKey } from "./cache.ts";
import { scratch } from "./support.ts";

const KEY = cacheKey("0.3.0", "C:/project");

test("a saved entry is loaded back with its time and value", () => {
  const { dir, cleanup } = scratch();
  try {
    const cache = new Cache(join(dir, "cache"));
    cache.save("snippets", { savedAt: "2026-09-20T10:00:00.000Z", key: KEY, value: { rows: [1] } });
    const entry = cache.load<{ rows: number[] }>("snippets", KEY);
    assert.deepEqual(entry, {
      savedAt: "2026-09-20T10:00:00.000Z",
      key: KEY,
      value: { rows: [1] },
    });
  } finally {
    cleanup();
  }
});

test("nothing saved reads as absent", () => {
  const { dir, cleanup } = scratch();
  try {
    assert.equal(new Cache(join(dir, "cache")).load("snippets", KEY), null);
  } finally {
    cleanup();
  }
});

test("an entry made under another key is discarded, for example after a command line update", () => {
  const { dir, cleanup } = scratch();
  try {
    const cache = new Cache(dir);
    cache.save("snippets", { savedAt: "t", key: cacheKey("0.3.0", "x"), value: 1 });
    assert.equal(cache.load("snippets", cacheKey("0.4.0", "x")), null);
    assert.equal(existsSync(join(dir, "snippets.json")), false, "the stale file is removed");
  } finally {
    cleanup();
  }
});

test("a corrupt file reads as absent and is removed", () => {
  const { dir, cleanup } = scratch();
  try {
    writeFileSync(join(dir, "snippets.json"), "{ not json");
    const cache = new Cache(dir);
    assert.equal(cache.load("snippets", KEY), null);
    assert.equal(existsSync(join(dir, "snippets.json")), false);
  } finally {
    cleanup();
  }
});

test("a file of the wrong shape or format reads as absent", () => {
  const { dir, cleanup } = scratch();
  try {
    const cache = new Cache(dir);
    writeFileSync(
      join(dir, "a.json"),
      JSON.stringify({ format: 99, savedAt: "t", key: KEY, value: 1 }),
    );
    writeFileSync(join(dir, "b.json"), JSON.stringify({ format: 1, key: KEY, value: 1 }));
    writeFileSync(join(dir, "c.json"), "null");
    assert.equal(cache.load("a", KEY), null);
    assert.equal(cache.load("b", KEY), null);
    assert.equal(cache.load("c", KEY), null);
  } finally {
    cleanup();
  }
});

test("saving leaves no temporary file behind and replaces an earlier entry", () => {
  const { dir, cleanup } = scratch();
  try {
    const cache = new Cache(dir);
    cache.save("health", { savedAt: "one", key: KEY, value: 1 });
    cache.save("health", { savedAt: "two", key: KEY, value: 2 });
    assert.deepEqual(readdirSync(dir), ["health.json"]);
    assert.equal(cache.load<number>("health", KEY)?.value, 2);
  } finally {
    cleanup();
  }
});

test("the cache only writes inside the directory it was given", () => {
  const { dir, cleanup } = scratch();
  try {
    const cacheDirectory = join(dir, "storage");
    const cache = new Cache(cacheDirectory);
    cache.save("snippets", { savedAt: "t", key: KEY, value: 1 });
    assert.deepEqual(readdirSync(dir), ["storage"]);
  } finally {
    cleanup();
  }
});
