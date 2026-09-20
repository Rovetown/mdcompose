import assert from "node:assert/strict";
import { join } from "node:path";
import { test } from "node:test";
import { Cache, cacheKey } from "./cache.ts";
import { fromCache, refresh } from "./refresh.ts";
import { fail, ok, type Failure } from "./result.ts";
import { scratch } from "./support.ts";

const KEY = cacheKey("0.3.0", "C:/project");
const FAILURE: Failure = { kind: "timeout", message: "did not finish" };
const NOW = () => new Date("2026-09-20T12:00:00.000Z");

interface Library {
  library: string;
}

function setup() {
  const { dir, cleanup } = scratch();
  return { cache: new Cache(join(dir, "cache")), cleanup };
}

test("a successful read is returned fresh and replaces the cache", async () => {
  const { cache, cleanup } = setup();
  try {
    const snapshot = await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: NOW,
      read: () => Promise.resolve(ok({ library: "/a" })),
    });
    assert.deepEqual(snapshot, {
      state: "fresh",
      value: { library: "/a" },
      readAt: "2026-09-20T12:00:00.000Z",
    });
    assert.deepEqual(cache.load<Library>("snippets", KEY)?.value, { library: "/a" });
  } finally {
    cleanup();
  }
});

test("at start the cached state is shown at once with the time it was read", async () => {
  const { cache, cleanup } = setup();
  try {
    await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: NOW,
      read: () => Promise.resolve(ok({ library: "/a" })),
    });
    const snapshot = fromCache<Library>(cache, "snippets", KEY);
    assert.deepEqual(snapshot, {
      state: "cached",
      value: { library: "/a" },
      readAt: "2026-09-20T12:00:00.000Z",
    });
  } finally {
    cleanup();
  }
});

test("with no cache there is nothing to show at start", () => {
  const { cache, cleanup } = setup();
  try {
    assert.equal(fromCache(cache, "snippets", KEY), null);
  } finally {
    cleanup();
  }
});

test("a failed refresh keeps showing the last good read together with the error", async () => {
  const { cache, cleanup } = setup();
  try {
    await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: NOW,
      read: () => Promise.resolve(ok({ library: "/a" })),
    });
    const snapshot = await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: () => new Date("2026-09-20T13:00:00.000Z"),
      read: () => Promise.resolve(fail(FAILURE)),
    });
    assert.deepEqual(snapshot, {
      state: "stale",
      value: { library: "/a" },
      readAt: "2026-09-20T12:00:00.000Z",
      error: FAILURE,
    });
    assert.equal(cache.load<Library>("snippets", KEY)?.savedAt, "2026-09-20T12:00:00.000Z");
  } finally {
    cleanup();
  }
});

test("a failed refresh with no cache is unavailable", async () => {
  const { cache, cleanup } = setup();
  try {
    const snapshot = await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: NOW,
      read: () => Promise.resolve(fail(FAILURE)),
    });
    assert.deepEqual(snapshot, { state: "unavailable", error: FAILURE });
  } finally {
    cleanup();
  }
});

test("a command line update discards the cache, so a failed refresh shows nothing stale", async () => {
  const { cache, cleanup } = setup();
  try {
    await refresh<Library>({
      cache,
      name: "snippets",
      key: cacheKey("0.3.0", "C:/project"),
      now: NOW,
      read: () => Promise.resolve(ok({ library: "/a" })),
    });
    const snapshot = await refresh<Library>({
      cache,
      name: "snippets",
      key: cacheKey("0.4.0", "C:/project"),
      now: NOW,
      read: () => Promise.resolve(fail(FAILURE)),
    });
    assert.equal(snapshot.state, "unavailable");
  } finally {
    cleanup();
  }
});

test("when the library has moved, the fresh read replaces the old rows", async () => {
  const { cache, cleanup } = setup();
  try {
    await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: NOW,
      read: () => Promise.resolve(ok({ library: "/old" })),
    });
    const snapshot = await refresh<Library>({
      cache,
      name: "snippets",
      key: KEY,
      now: NOW,
      read: () => Promise.resolve(ok({ library: "/new" })),
    });
    assert.equal(snapshot.state, "fresh");
    assert.deepEqual(cache.load<Library>("snippets", KEY)?.value, { library: "/new" });
  } finally {
    cleanup();
  }
});
