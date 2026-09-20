import type { Content, LibraryKind } from "./model.ts";

// Short explanations added to what the views already show. This whole feature is
// one file, its test, and two calls in controller.ts, so it can be removed by
// deleting those and nothing else. It only rewrites text: it never changes which
// rows exist, their ids, or their icons.

const FILE_HINTS: Record<string, string> = {
  clean: "matches the manifest",
  drifted: "edited by hand",
  missing: "file is gone",
  "block-removed": "managed block was removed",
  malformed: "markers no longer parse",
};

const TARGET_HINTS: Record<string, string> = {
  "in-sync": "matches the project",
  "out-of-sync": "differs from the project",
  missing: "file is gone",
  malformed: "markers no longer parse",
};

function explain(status: string, hints: Record<string, string>): string {
  const hint = hints[status];
  return hint === undefined ? status : `${status} - ${hint}`;
}

export function withLibraryHints(content: Content, kind: LibraryKind): Content {
  const empty = `The ${kind} library is empty.`;
  if (content.rows.length > 0 || !(content.message ?? "").startsWith(empty)) return content;
  const next =
    `Use Adopt in the title bar to copy the ${kind}s a project uses into this library, ` +
    "or add files to the folder by hand.";
  return { ...content, message: `${content.message} ${next}` };
}

export function withProjectHints(content: Content): Content {
  const rows = content.rows.map((row) => {
    if (row.id.startsWith("health:file:")) {
      return { ...row, description: explain(row.description, FILE_HINTS) };
    }
    if (row.id.startsWith("health:target:")) {
      return { ...row, description: explain(row.description, TARGET_HINTS) };
    }
    return row;
  });
  return { ...content, rows };
}
