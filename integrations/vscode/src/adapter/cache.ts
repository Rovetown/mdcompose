import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// A display cache of what the command line last reported, kept so the sidebar
// can show something at once on start. It lives in a directory the caller
// supplies, which the extension points at the editor's own storage area and never
// at the snippet library, the skill library, or a project. It is never the
// source of truth: every successful refresh replaces it.

const FORMAT = 1;

export interface CacheEntry<T> {
  savedAt: string;
  // Identifies what produced the document. An entry whose key differs from the
  // current one is discarded, for example after the command line is updated.
  key: string;
  value: T;
}

interface Stored<T> extends CacheEntry<T> {
  format: number;
}

export class Cache {
  // Declared plainly, not as a constructor parameter property, because Node's
  // type-stripping test runner cannot run parameter properties.
  private readonly directory: string;

  constructor(directory: string) {
    this.directory = directory;
  }

  private fileFor(name: string): string {
    return join(this.directory, `${name}.json`);
  }

  // Returns the entry for `name` if it exists, is readable, and was made under
  // the same key. A corrupt file, or one made under another key, is removed and
  // reads as absent.
  load<T>(name: string, key: string): CacheEntry<T> | null {
    const file = this.fileFor(name);
    let stored: Stored<T>;
    try {
      stored = JSON.parse(readFileSync(file, "utf8")) as Stored<T>;
    } catch {
      this.discard(name);
      return null;
    }
    const valid =
      typeof stored === "object" &&
      stored !== null &&
      stored.format === FORMAT &&
      typeof stored.savedAt === "string" &&
      typeof stored.key === "string" &&
      "value" in stored;
    if (!valid || stored.key !== key) {
      this.discard(name);
      return null;
    }
    return { savedAt: stored.savedAt, key: stored.key, value: stored.value };
  }

  // Written to a temporary file and renamed into place, so a reader never sees a
  // half-written file.
  save<T>(name: string, entry: CacheEntry<T>): void {
    mkdirSync(this.directory, { recursive: true });
    const file = this.fileFor(name);
    const temporary = `${file}.${process.pid}.tmp`;
    const stored: Stored<T> = { format: FORMAT, ...entry };
    writeFileSync(temporary, JSON.stringify(stored), "utf8");
    renameSync(temporary, file);
  }

  discard(name: string): void {
    rmSync(this.fileFor(name), { force: true });
  }
}

// What identifies a cached document: the command line version and where it ran.
export function cacheKey(cliVersion: string, scope: string): string {
  return `${cliVersion.trim()}|${scope}`;
}
