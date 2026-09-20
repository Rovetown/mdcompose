import assert from "node:assert/strict";
import { test } from "node:test";
import type { HealthState } from "../adapter/commands.ts";
import {
  readHealth,
  readSkillList,
  readSnippetList,
  type LibraryReport,
} from "../adapter/reports.ts";
import type { Snapshot } from "../adapter/refresh.ts";
import { isAscii, sample } from "../adapter/support.ts";
import { healthContent, libraryContent } from "./model.ts";

const format = (iso: string): string => `at ${iso}`;
const READ_AT = "2026-09-20T12:00:00.000Z";

function snippets(): LibraryReport {
  const result = readSnippetList(sample("snippet-list"));
  assert.ok(result.ok);
  return result.value;
}

function fresh<T>(value: T): Snapshot<T> {
  return { state: "fresh", value, readAt: READ_AT };
}

function healthState(attention: boolean): HealthState {
  const report = readHealth(sample("doctor"));
  assert.ok(report.ok);
  return { report: report.value, attention };
}

test("a populated library shows one row per entry with title and tags", () => {
  const content = libraryContent(fresh(snippets()), "snippet", format);
  assert.equal(content.rows.length, 2);
  assert.equal(content.message, undefined);
  const commit = content.rows.find((row) => row.id === "snippet:commit-style");
  assert.equal(commit?.label, "Commit style");
  assert.equal(commit?.description, "git, conventions");
  assert.match(commit?.tooltip ?? "", /How commits are written here/);
  assert.equal(commit?.contextValue, "snippet");
});

test("an empty library says so and says where it is", () => {
  const empty: LibraryReport = { library: "/home/me/snippets", entries: [] };
  const content = libraryContent(fresh(empty), "snippet", format);
  assert.deepEqual(content.rows, []);
  assert.match(content.message ?? "", /snippet library is empty/);
  assert.match(content.message ?? "", /\/home\/me\/snippets/);
});

test("entries that share a title are told apart by their ids", () => {
  const report: LibraryReport = {
    library: "/lib",
    entries: [
      { id: "a", title: "Style", description: null, tags: ["x"], category: null, isBundle: false },
      { id: "b", title: "Style", description: null, tags: [], category: null, isBundle: false },
      { id: "c", title: "Other", description: null, tags: [], category: null, isBundle: false },
    ],
  };
  const rows = libraryContent(fresh(report), "snippet", format).rows;
  assert.equal(rows[0]?.description, "a - x");
  assert.equal(rows[1]?.description, "b");
  assert.equal(rows[2]?.description, "");
});

test("an entry without a title is shown by its id", () => {
  const report: LibraryReport = {
    library: "/lib",
    entries: [
      { id: "bare", title: "", description: null, tags: [], category: null, isBundle: false },
    ],
  };
  assert.equal(libraryContent(fresh(report), "skill", format).rows[0]?.label, "bare");
});

test("a bundle skill gets a folder icon and says it is a directory", () => {
  const result = readSkillList({
    library: "/lib",
    skills: [
      {
        id: "release",
        title: "Release",
        description: null,
        tags: [],
        category: null,
        is_bundle: true,
      },
    ],
  });
  assert.ok(result.ok);
  const row = libraryContent(fresh(result.value), "skill", format).rows[0];
  assert.equal(row?.icon, "folder");
  assert.match(row?.tooltip ?? "", /directory/);
  assert.equal(row?.contextValue, "skill");
});

test("nothing loaded yet reads as loading", () => {
  assert.equal(libraryContent(null, "snippet", format).message, "Loading.");
});

test("cached rows are shown at once with the time they were read, and say a refresh follows", () => {
  const snapshot: Snapshot<LibraryReport> = { state: "cached", value: snippets(), readAt: READ_AT };
  const content = libraryContent(snapshot, "snippet", format);
  assert.equal(content.rows.length, 2);
  assert.match(content.message ?? "", /Showing what was read at 2026-09-20T12:00:00.000Z/);
  assert.match(content.message ?? "", /Refreshing/);
});

test("a failed refresh keeps the rows and shows the error and the last good time", () => {
  const snapshot: Snapshot<LibraryReport> = {
    state: "stale",
    value: snippets(),
    readAt: READ_AT,
    error: { kind: "timeout", message: "mdcompose did not finish." },
  };
  const content = libraryContent(snapshot, "snippet", format);
  assert.equal(content.rows.length, 2);
  assert.match(content.message ?? "", /Refresh failed: mdcompose did not finish\./);
  assert.match(content.message ?? "", /at 2026-09-20T12:00:00.000Z/);
});

test("with no cache and a failed read there are no rows and the error is shown", () => {
  const snapshot: Snapshot<LibraryReport> = {
    state: "unavailable",
    error: { kind: "incompatible", missing: ["library"], message: "Not compatible." },
  };
  const content = libraryContent(snapshot, "skill", format);
  assert.deepEqual(content.rows, []);
  assert.match(content.message ?? "", /Could not read the skill library: Not compatible\./);
});

test("a healthy project shows a healthy row and its files", () => {
  const content = healthContent(fresh(healthState(false)), true, format);
  assert.equal(content.rows[0]?.label, "Healthy");
  assert.equal(content.rows[0]?.icon, "pass");
  const files = content.rows.filter((row) => row.contextValue === "file").map((row) => row.label);
  assert.deepEqual(files, ["AGENTS.md", "CLAUDE.md"]);
});

test("a project with a condition shows needs attention, and an out-of-sync target is a warning", () => {
  const content = healthContent(fresh(healthState(true)), true, format);
  assert.equal(content.rows[0]?.label, "Needs attention");
  assert.equal(content.rows[0]?.icon, "warning");
  const target = content.rows.find((row) => row.contextValue === "target");
  assert.equal(target?.label, "Target: codex");
  assert.equal(target?.description, "missing");
  assert.equal(target?.icon, "warning");
});

test("a project that was never composed says so", () => {
  const state = healthState(false);
  state.report.drift = null;
  const content = healthContent(fresh(state), true, format);
  assert.ok(content.rows.some((row) => row.label === "Not composed yet"));
});

test("warnings from the report each get a row", () => {
  const state = healthState(false);
  state.report.warnings = ["the config directory is inside OneDrive"];
  const rows = healthContent(fresh(state), true, format).rows;
  const warning = rows.find((row) => row.contextValue === "warning");
  assert.equal(warning?.description, "the config directory is inside OneDrive");
  assert.equal(warning?.icon, "warning");
});

test("a window with no folder open says so", () => {
  const content = healthContent(null, false, format);
  assert.deepEqual(content.rows, []);
  assert.match(content.message ?? "", /Open a folder/);
});

test("every string the views generate is plain ASCII", () => {
  const contents = [
    libraryContent(fresh(snippets()), "snippet", format),
    healthContent(fresh(healthState(true)), true, format),
    healthContent(null, false, format),
    libraryContent(null, "skill", format),
  ];
  for (const content of contents) {
    const texts = [
      content.message ?? "",
      ...content.rows.flatMap((row) => [row.label, row.description, row.tooltip]),
    ];
    for (const text of texts) assert.ok(isAscii(text), text);
  }
});
