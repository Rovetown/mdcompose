import * as vscode from "vscode";
import type { CollisionChoice } from "./adapter/actions.ts";
import type { LibraryEntry } from "./adapter/reports.ts";

// Every question the actions put to the user. They are behind an interface so the
// editor tests can answer them, since a modal dialog cannot be clicked from a
// test. The defaults below are the real dialogs.

export type CollisionAnswer = CollisionChoice | "terminal" | undefined;

export interface Prompts {
  confirmRemove: (kind: string, title: string, id: string) => Promise<boolean>;
  chooseCollision: (kind: string) => Promise<CollisionAnswer>;
  // A question with one button, for example to continue in the terminal.
  offer: (message: string, button: string) => Promise<boolean>;
  pickEntry: (kind: string, entries: readonly LibraryEntry[]) => Promise<string | undefined>;
  pickFolder: () => Promise<string | undefined>;
}

const KEEP = "Keep Library Copies";
const REPLACE = "Replace With Project Copies";
const TERMINAL = "Decide in Terminal";

export const defaultPrompts: Prompts = {
  async confirmRemove(kind, title, id) {
    const answer = await vscode.window.showWarningMessage(
      `Remove the ${kind} "${title}" from your library?`,
      {
        modal: true,
        detail: `Its id is ${id}. Files already composed into projects are not changed.`,
      },
      "Remove",
    );
    return answer === "Remove";
  },

  async chooseCollision(kind) {
    const answer = await vscode.window.showWarningMessage(
      `Some ${kind}s already exist in your library with different content.`,
      {
        modal: true,
        detail:
          "Nothing has been changed yet. Keep your library copies, replace them with the " +
          "project's copies, or go through them one by one in the terminal.",
      },
      KEEP,
      REPLACE,
      TERMINAL,
    );
    if (answer === KEEP) return "keep";
    if (answer === REPLACE) return "overwrite";
    if (answer === TERMINAL) return "terminal";
    return undefined;
  },

  async offer(message, button) {
    return (await vscode.window.showWarningMessage(message, button)) === button;
  },

  async pickEntry(kind, entries) {
    const items = entries.map((entry) => ({
      label: entry.title === "" ? entry.id : entry.title,
      description: entry.id,
      id: entry.id,
    }));
    const picked = await vscode.window.showQuickPick(items, { placeHolder: `Choose a ${kind}` });
    return picked?.id;
  },

  async pickFolder() {
    return (await vscode.window.showWorkspaceFolderPick())?.uri.fsPath;
  },
};
