import type { HealthState } from "../adapter/commands.ts";
import type { LibraryEntry, LibraryReport } from "../adapter/reports.ts";
import type { Snapshot } from "../adapter/refresh.ts";

// What each view shows, as plain data. Nothing here touches the editor, so the
// wording and the rules (which icon, when an id is shown) are unit tested. The
// tree providers only translate these rows into tree items.

// Names of the editor's built-in icons, so no icon files are shipped for rows.
export type IconId = "pass" | "warning" | "info" | "file-code" | "sparkle" | "folder";

export interface Row {
  id: string;
  label: string;
  description: string;
  tooltip: string;
  icon: IconId;
  // Lets menus and commands target rows of one kind.
  contextValue: string;
  // The library id, on rows that stand for a snippet or a skill.
  entryId?: string;
}

export interface Content {
  rows: Row[];
  // Shown above the rows: the state of the data, or why there are none.
  message: string | undefined;
}

export type LibraryKind = "snippet" | "skill";

export type FormatTime = (iso: string) => string;

const LOADING: Content = { rows: [], message: "Loading." };

function libraryRow(kind: LibraryKind, entry: LibraryEntry, titleIsShared: boolean): Row {
  const parts: string[] = [];
  // Two entries with the same title are told apart by their ids.
  if (titleIsShared) parts.push(entry.id);
  if (entry.tags.length > 0) parts.push(entry.tags.join(", "));
  const title = entry.title === "" ? entry.id : entry.title;
  const details = [
    title,
    ...(entry.description === null ? [] : [entry.description]),
    `id: ${entry.id}`,
    ...(entry.category === null ? [] : [`category: ${entry.category}`]),
    ...(entry.tags.length === 0 ? [] : [`tags: ${entry.tags.join(", ")}`]),
    ...(entry.isBundle ? ["a skill stored as a directory"] : []),
  ];
  let icon: IconId = kind === "snippet" ? "file-code" : "sparkle";
  if (entry.isBundle) icon = "folder";
  return {
    id: `${kind}:${entry.id}`,
    label: title,
    description: parts.join(" - "),
    tooltip: details.join("\n"),
    icon,
    contextValue: kind,
    entryId: entry.id,
  };
}

function libraryRows(kind: LibraryKind, report: LibraryReport): Row[] {
  const counts = new Map<string, number>();
  for (const entry of report.entries) {
    const title = entry.title === "" ? entry.id : entry.title;
    counts.set(title, (counts.get(title) ?? 0) + 1);
  }
  return report.entries.map((entry) => {
    const title = entry.title === "" ? entry.id : entry.title;
    return libraryRow(kind, entry, (counts.get(title) ?? 0) > 1);
  });
}

// The message above the rows for a snapshot of any kind.
function stateMessage<T>(
  snapshot: Snapshot<T>,
  what: string,
  format: FormatTime,
): string | undefined {
  switch (snapshot.state) {
    case "fresh":
      return undefined;
    case "cached":
      return `Showing what was read ${format(snapshot.readAt)}. Refreshing.`;
    case "stale":
      return `Refresh failed: ${snapshot.error.message} Showing what was read ${format(snapshot.readAt)}.`;
    case "unavailable":
      return `Could not read ${what}: ${snapshot.error.message}`;
  }
}

export function libraryContent(
  snapshot: Snapshot<LibraryReport> | null,
  kind: LibraryKind,
  format: FormatTime,
): Content {
  if (snapshot === null) return LOADING;
  if (snapshot.state === "unavailable") {
    return { rows: [], message: stateMessage(snapshot, `the ${kind} library`, format) };
  }
  const rows = libraryRows(kind, snapshot.value);
  const message = stateMessage(snapshot, `the ${kind} library`, format);
  if (rows.length === 0) {
    const empty = `The ${kind} library is empty. It is at ${snapshot.value.library}.`;
    return { rows, message: message === undefined ? empty : `${empty} ${message}` };
  }
  return { rows, message };
}

const FILE_LABELS: Record<string, string> = {
  agents_md: "AGENTS.md",
  claude_md: "CLAUDE.md",
};

// The name shown for a managed file, given the key the command line reports.
export function fileLabel(key: string): string {
  return FILE_LABELS[key] ?? key;
}

const TARGET_OK = "in-sync";

export function healthContent(
  snapshot: Snapshot<HealthState> | null,
  hasFolder: boolean,
  format: FormatTime,
): Content {
  if (!hasFolder) return { rows: [], message: "Open a folder to see its mdcompose state." };
  if (snapshot === null) return LOADING;
  if (snapshot.state === "unavailable") {
    return { rows: [], message: stateMessage(snapshot, "the project state", format) };
  }
  const { report, attention } = snapshot.value;
  const rows: Row[] = [];
  rows.push({
    id: "health:overall",
    label: attention ? "Needs attention" : "Healthy",
    description: `${report.os}${report.wsl ? " (WSL)" : ""}`,
    tooltip: attention
      ? "mdcompose found a condition to resolve. Details are in the rows below."
      : "mdcompose found nothing to resolve.",
    icon: attention ? "warning" : "pass",
    contextValue: "health",
  });
  if (report.drift === null) {
    rows.push({
      id: "health:not-composed",
      label: "Not composed yet",
      description: "run init in this project",
      tooltip: "This project has no mdcompose manifest.",
      icon: "info",
      contextValue: "file",
    });
  } else {
    for (const entry of report.drift) {
      const label = fileLabel(entry.file);
      const clean = entry.status === "clean";
      rows.push({
        id: `health:file:${entry.file}`,
        label,
        description: entry.status,
        tooltip: [
          label,
          `status: ${entry.status}`,
          ...(entry.detail === null ? [] : [entry.detail]),
        ].join("\n"),
        icon: clean ? "pass" : "warning",
        contextValue: "file",
      });
    }
  }
  for (const target of report.targets) {
    rows.push({
      id: `health:target:${target.label}`,
      label: `Target: ${target.label}`,
      description: target.sync,
      tooltip: [
        `target: ${target.label}`,
        `sync: ${target.sync}`,
        ...(target.path === null ? [] : [target.path]),
      ].join("\n"),
      icon: target.sync === TARGET_OK ? "pass" : "warning",
      contextValue: "target",
    });
  }
  report.warnings.forEach((warning, index) => {
    rows.push({
      id: `health:warning:${index}`,
      label: "Warning",
      description: warning,
      tooltip: warning,
      icon: "warning",
      contextValue: "warning",
    });
  });
  return { rows, message: stateMessage(snapshot, "the project state", format) };
}
