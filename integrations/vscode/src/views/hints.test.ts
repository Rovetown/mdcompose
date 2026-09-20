import assert from "node:assert/strict";
import { test } from "node:test";
import type { HealthState } from "../adapter/commands.ts";
import { readHealth, readSnippetList } from "../adapter/reports.ts";
import type { Snapshot } from "../adapter/refresh.ts";
import { isAscii, sample } from "../adapter/support.ts";
import { withLibraryHints, withProjectHints } from "./hints.ts";
import { healthContent, libraryContent } from "./model.ts";

const format = (iso: string): string => `at ${iso}`;
const READ_AT = "2026-09-20T12:00:00.000Z";

function fresh<T>(value: T): Snapshot<T> {
  return { state: "fresh", value, readAt: READ_AT };
}

function health(): HealthState {
  const report = readHealth(sample("doctor"));
  assert.ok(report.ok);
  return { report: report.value, attention: false };
}

function emptyLibrary() {
  const list = readSnippetList(sample("snippet-list"));
  assert.ok(list.ok);
  return libraryContent(fresh({ ...list.value, entries: [] }), "snippet", format);
}

test("an empty library says how to fill it", () => {
  const content = withLibraryHints(emptyLibrary(), "snippet");
  assert.match(content.message ?? "", /Adopt/);
  assert.ok(isAscii(content.message ?? ""));
});

test("a library with entries is left as it was", () => {
  const list = readSnippetList(sample("snippet-list"));
  assert.ok(list.ok);
  const content = libraryContent(fresh(list.value), "snippet", format);
  assert.equal(withLibraryHints(content, "snippet"), content);
});

test("an error message is left as it was", () => {
  const content = libraryContent(
    { state: "unavailable", error: { kind: "failed", message: "boom" } as never },
    "snippet",
    format,
  );
  assert.equal(withLibraryHints(content, "snippet"), content);
});

test("project rows keep their ids, labels, and icons, and only the description grows", () => {
  const before = healthContent(fresh(health()), true, format);
  const after = withProjectHints(before);
  assert.equal(after.rows.length, before.rows.length);
  after.rows.forEach((row, index) => {
    const original = before.rows[index];
    assert.equal(row.id, original?.id);
    assert.equal(row.label, original?.label);
    assert.equal(row.icon, original?.icon);
    assert.equal(row.tooltip, original?.tooltip);
    assert.ok(row.description.startsWith(original?.description ?? "?"), row.id);
  });
});

test("a clean file and a missing target are explained", () => {
  const after = withProjectHints(healthContent(fresh(health()), true, format));
  const file = after.rows.find((row) => row.id.startsWith("health:file:"));
  assert.match(file?.description ?? "", /^clean - matches the manifest$/);
  const target = after.rows.find((row) => row.id.startsWith("health:target:"));
  assert.match(target?.description ?? "", /^missing - file is gone$/);
});

test("a status with no hint is shown unchanged", () => {
  const before = healthContent(fresh(health()), true, format);
  const odd = { ...before, rows: before.rows.map((row) => ({ ...row, description: "novel" })) };
  const after = withProjectHints(odd);
  for (const row of after.rows) assert.equal(row.description, "novel");
});

test("every hint is plain ASCII", () => {
  const after = withProjectHints(healthContent(fresh(health()), true, format));
  for (const row of after.rows) assert.ok(isAscii(row.description), row.id);
});
