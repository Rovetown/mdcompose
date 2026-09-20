import assert from "node:assert/strict";
import { join } from "node:path";
import { test } from "node:test";
import { entryFile, readHealth, readSkillList, readSnippetList } from "./reports.ts";
import { sample } from "./support.ts";

test("the shared snippet sample is read into library entries", () => {
  const result = readSnippetList(sample("snippet-list"));
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.entries.length, 2);
  const commit = result.value.entries.find((entry) => entry.id === "commit-style");
  assert.equal(commit?.title, "Commit style");
  assert.deepEqual(commit?.tags, ["git", "conventions"]);
  assert.equal(commit?.category, "conventions");
  assert.equal(commit?.isBundle, false);
});

test("the shared skill sample is read, including whether a skill is a bundle", () => {
  const result = readSkillList(sample("skill-list"));
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.entries[0]?.id, "code-review");
  assert.equal(result.value.entries[0]?.isBundle, false);
});

test("the shared doctor sample is read, with its targets and drift", () => {
  const result = readHealth(sample("doctor"));
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.initialized, true);
  assert.equal(result.value.targets[0]?.sync, "missing");
  assert.equal(result.value.drift?.length, 2);
  assert.ok(result.value.paths.some((entry) => entry.label === "snippet library"));
});

test("a field the command line adds later is ignored", () => {
  const document = sample("snippet-list") as { snippets: Record<string, unknown>[] };
  document.snippets[0] = { ...document.snippets[0], brand_new_field: [1, 2, 3] };
  const result = readSnippetList({ ...document, another_new_field: true });
  assert.equal(result.ok, true);
});

test("a missing needed field makes the report incompatible and names the field", () => {
  const document = sample("snippet-list") as { snippets: Record<string, unknown>[] };
  const { title: _removed, ...withoutTitle } = document.snippets[0] ?? {};
  const result = readSnippetList({ ...document, snippets: [withoutTitle] });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.error.kind, "incompatible");
  if (result.error.kind === "incompatible") {
    assert.deepEqual(result.error.missing, ["snippets[].title"]);
  }
  assert.match(result.error.message, /not compatible/);
});

test("a field of the wrong type is treated as missing, with no default invented", () => {
  const result = readSnippetList({ library: 5, snippets: "nope" });
  assert.equal(result.ok, false);
  if (!result.ok && result.error.kind === "incompatible") {
    assert.deepEqual(result.error.missing.sort(), ["library", "snippets"]);
  }
});

test("a report that is not an object at all is incompatible", () => {
  assert.equal(readSnippetList([]).ok, false);
  assert.equal(readSnippetList(null).ok, false);
  assert.equal(readHealth("text").ok, false);
});

test("a field that has no value must be present and null, not absent", () => {
  const document = sample("snippet-list") as { snippets: Record<string, unknown>[] };
  const entry = { ...document.snippets[0] };
  delete entry["description"];
  assert.equal(readSnippetList({ ...document, snippets: [entry] }).ok, false);
});

test("a project that has not been composed reports no drift list", () => {
  const document = sample("doctor") as Record<string, unknown>;
  const result = readHealth({ ...document, initialized: false, drift: null });
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.value.drift, null);
});

test("a path that is not configured is null and still readable", () => {
  const document = sample("doctor") as { paths: Record<string, unknown>[] };
  const paths = [
    ...document.paths,
    { label: "global AGENTS.md", status: "not configured", path: null },
  ];
  assert.equal(readHealth({ ...document, paths }).ok, true);
});

test("an entry's file is named for its id, and a bundle skill is a directory", () => {
  const plain = {
    id: "review",
    title: "",
    description: null,
    tags: [],
    category: null,
    isBundle: false,
  };
  const bundle = { ...plain, id: "release", isBundle: true };
  assert.equal(entryFile("snippet", "/lib", plain), join("/lib", "review.md"));
  assert.equal(entryFile("skill", "/lib", plain), join("/lib", "review.md"));
  assert.equal(entryFile("skill", "/lib", bundle), join("/lib", "release", "SKILL.md"));
});
