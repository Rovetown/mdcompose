import assert from "node:assert/strict";
import { test } from "node:test";
import { formatLocal } from "./time.ts";

test("a time is shown as local date and hour and minute", () => {
  const local = new Date(2026, 8, 20, 14, 5, 30);
  assert.equal(formatLocal(local.toISOString()), "2026-09-20 14:05");
});

test("single digits are padded", () => {
  const local = new Date(2026, 0, 2, 3, 4);
  assert.equal(formatLocal(local.toISOString()), "2026-01-02 03:04");
});

test("text that is not a time is returned unchanged", () => {
  assert.equal(formatLocal("not a time"), "not a time");
});

test("the result is plain ASCII", () => {
  assert.match(formatLocal(new Date().toISOString()), /^[0-9 :-]+$/);
});
