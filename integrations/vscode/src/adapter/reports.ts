import { join } from "node:path";
import { fail, ok, type Failure, type Result } from "./result.ts";

// Readers for the reports the extension shows. Each reads only the fields it
// needs and ignores the rest, so a field the command line adds later changes
// nothing here. A field it needs that is missing or of the wrong type makes the
// whole report incompatible, and no default is invented.

export interface LibraryEntry {
  id: string;
  title: string;
  description: string | null;
  tags: string[];
  category: string | null;
  // Skills only: a skill stored as a directory holding SKILL.md and other files.
  isBundle: boolean;
}

export interface LibraryReport {
  library: string;
  entries: LibraryEntry[];
}

export interface HealthPath {
  label: string;
  status: string;
  path: string | null;
}

export interface HealthDrift {
  file: string;
  path: string | null;
  status: string;
  detail: string | null;
}

export interface HealthTarget {
  label: string;
  path: string | null;
  present: boolean;
  sync: string;
}

export interface HealthReport {
  os: string;
  wsl: boolean;
  initialized: boolean;
  warnings: string[];
  paths: HealthPath[];
  // Null when the project has not been composed.
  drift: HealthDrift[] | null;
  targets: HealthTarget[];
}

type Record_ = Record<string, unknown>;

// Collects every problem before failing, so the message names all of them.
class Reader {
  readonly problems: string[] = [];

  record(value: unknown, path: string): Record_ {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return value as Record_;
    }
    this.problems.push(path);
    return {};
  }

  string(from: Record_, key: string, path: string): string {
    const value = from[key];
    if (typeof value === "string") return value;
    this.problems.push(`${path}${key}`);
    return "";
  }

  nullableString(from: Record_, key: string, path: string): string | null {
    const value = from[key];
    if (value === null || typeof value === "string") return value;
    this.problems.push(`${path}${key}`);
    return null;
  }

  boolean(from: Record_, key: string, path: string): boolean {
    const value = from[key];
    if (typeof value === "boolean") return value;
    this.problems.push(`${path}${key}`);
    return false;
  }

  array(from: Record_, key: string, path: string): unknown[] {
    const value = from[key];
    if (Array.isArray(value)) return value;
    this.problems.push(`${path}${key}`);
    return [];
  }

  strings(from: Record_, key: string, path: string): string[] {
    return this.array(from, key, path).filter((item): item is string => {
      if (typeof item === "string") return true;
      this.problems.push(`${path}${key}[]`);
      return false;
    });
  }

  done<T>(value: T): Result<T, Failure> {
    if (this.problems.length === 0) return ok(value);
    const missing = [...new Set(this.problems)];
    return fail({
      kind: "incompatible",
      missing,
      message:
        "This version of mdcompose is not compatible with the extension: " +
        `its report lacks or changes ${missing.join(", ")}.`,
    });
  }
}

function readLibrary(
  document: unknown,
  listKey: string,
  withBundle: boolean,
): Result<LibraryReport, Failure> {
  const reader = new Reader();
  const root = reader.record(document, "the report");
  const library = reader.string(root, "library", "");
  const entries = reader.array(root, listKey, "").map((item) => {
    const row = reader.record(item, `${listKey}[]`);
    const path = `${listKey}[].`;
    return {
      id: reader.string(row, "id", path),
      title: reader.string(row, "title", path),
      description: reader.nullableString(row, "description", path),
      tags: reader.strings(row, "tags", path),
      category: reader.nullableString(row, "category", path),
      isBundle: withBundle ? reader.boolean(row, "is_bundle", path) : false,
    };
  });
  return reader.done({ library, entries });
}

export function readSnippetList(document: unknown): Result<LibraryReport, Failure> {
  return readLibrary(document, "snippets", false);
}

export function readSkillList(document: unknown): Result<LibraryReport, Failure> {
  return readLibrary(document, "skills", true);
}

export function readHealth(document: unknown): Result<HealthReport, Failure> {
  const reader = new Reader();
  const root = reader.record(document, "the report");
  const paths = reader.array(root, "paths", "").map((item) => {
    const row = reader.record(item, "paths[]");
    return {
      label: reader.string(row, "label", "paths[]."),
      status: reader.string(row, "status", "paths[]."),
      path: reader.nullableString(row, "path", "paths[]."),
    };
  });
  const targets = reader.array(root, "targets", "").map((item) => {
    const row = reader.record(item, "targets[]");
    return {
      label: reader.string(row, "label", "targets[]."),
      path: reader.nullableString(row, "path", "targets[]."),
      present: reader.boolean(row, "present", "targets[]."),
      sync: reader.string(row, "sync", "targets[]."),
    };
  });
  let drift: HealthDrift[] | null = null;
  if (root["drift"] === null) {
    drift = null;
  } else {
    drift = reader.array(root, "drift", "").map((item) => {
      const row = reader.record(item, "drift[]");
      return {
        file: reader.string(row, "file", "drift[]."),
        path: reader.nullableString(row, "path", "drift[]."),
        status: reader.string(row, "status", "drift[]."),
        detail: reader.nullableString(row, "detail", "drift[]."),
      };
    });
  }
  return reader.done({
    os: reader.string(root, "os", ""),
    wsl: reader.boolean(root, "wsl", ""),
    initialized: reader.boolean(root, "initialized", ""),
    warnings: reader.strings(root, "warnings", ""),
    paths,
    drift,
    targets,
  });
}

// The file that holds an entry. A snippet or plain skill is one Markdown file
// named for its id; a bundle skill is a directory with SKILL.md inside.
export function entryFile(kind: "snippet" | "skill", library: string, entry: LibraryEntry): string {
  if (kind === "skill" && entry.isBundle) return join(library, entry.id, "SKILL.md");
  return join(library, `${entry.id}.md`);
}
