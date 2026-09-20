import { existsSync } from "node:fs";
import * as vscode from "vscode";
import {
  adoptEntries,
  reapplyProject,
  removeEntry,
  type ActionOutcome,
  type LibraryKind,
} from "./adapter/actions.ts";
import { entryFile, type LibraryEntry } from "./adapter/reports.ts";
import type { Controller } from "./controller.ts";
import type { Prompts } from "./prompts.ts";
import { fileLabel, type Row } from "./views/model.ts";

// Every action is a command the command line already has. A button in a view and
// the matching command in the command palette are the same function, so they
// behave the same. From the palette there is no row to act on, so the entry is
// chosen from a list instead.

const INSTALL_HINT = "mdcompose is not ready. See the mdcompose view for what to do.";

export interface PromptsHolder {
  prompts: Prompts;
}

function say(outcome: ActionOutcome, controller: Controller): void {
  switch (outcome.kind) {
    case "done":
      void vscode.window.showInformationMessage(
        outcome.summary === "" ? "Done." : `mdcompose: ${outcome.summary}`,
      );
      return;
    case "needs-attention":
      controller.log(outcome.message);
      void vscode.window.showWarningMessage(`mdcompose: ${outcome.message}`);
      return;
    case "failed":
      controller.log(outcome.failure.message);
      void vscode.window.showErrorMessage(outcome.failure.message);
      return;
  }
}

// Actions that change files run only in a workspace the user has trusted. A
// repository the user has not trusted must not be able to make the extension write
// anything, so the buttons are hidden and the commands refuse.
function trusted(): boolean {
  if (vscode.workspace.isTrusted) return true;
  void vscode.window.showWarningMessage(
    "This workspace is not trusted, so mdcompose will not change any files here. " +
      "Trust the workspace to use this action.",
  );
  return false;
}

export function registerActions(
  context: vscode.ExtensionContext,
  controller: Controller,
  holder: PromptsHolder,
): void {
  const register = (command: string, handler: (...args: never[]) => unknown): void => {
    context.subscriptions.push(
      vscode.commands.registerCommand(command, handler as (...args: unknown[]) => unknown),
    );
  };

  // The entry an action applies to: the row it was started from, or one chosen
  // from a list when it was started from the command palette.
  async function chooseEntry(
    kind: LibraryKind,
    row: Row | undefined,
  ): Promise<LibraryEntry | undefined> {
    const library = controller.library(kind);
    if (library === undefined) {
      void vscode.window.showWarningMessage(INSTALL_HINT);
      return undefined;
    }
    const id = row?.entryId ?? (await holder.prompts.pickEntry(kind, library.entries));
    return library.entries.find((entry) => entry.id === id);
  }

  // The folder a project action applies to. A window with several folders asks.
  async function chooseFolder(): Promise<string | undefined> {
    const folders = vscode.workspace.workspaceFolders ?? [];
    if (folders.length === 0) {
      void vscode.window.showWarningMessage(
        "Open a folder first: this action applies to a project.",
      );
      return undefined;
    }
    const folder =
      folders.length === 1 ? folders[0]?.uri.fsPath : await holder.prompts.pickFolder();
    if (folder !== undefined) await controller.setFolder(folder);
    return folder;
  }

  function fileOf(kind: LibraryKind, entry: LibraryEntry): string | undefined {
    const library = controller.library(kind);
    return library === undefined ? undefined : entryFile(kind, library.library, entry);
  }

  async function edit(kind: LibraryKind, row: Row | undefined): Promise<void> {
    const entry = await chooseEntry(kind, row);
    if (entry === undefined) return;
    const file = fileOf(kind, entry);
    if (file === undefined || !existsSync(file)) {
      void vscode.window.showWarningMessage(
        `The file for "${entry.id}" is not where the last read said (${file ?? "unknown"}). Refresh the view.`,
      );
      return;
    }
    await vscode.window.showTextDocument(vscode.Uri.file(file));
  }

  async function remove(kind: LibraryKind, row: Row | undefined): Promise<void> {
    if (!trusted()) return;
    const entry = await chooseEntry(kind, row);
    if (entry === undefined) return;
    const title = entry.title === "" ? entry.id : entry.title;
    if (!(await holder.prompts.confirmRemove(kind, title, entry.id))) return;
    const run = controller.runIn(
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd(),
    );
    if (run === undefined) {
      void vscode.window.showWarningMessage(INSTALL_HINT);
      return;
    }
    say(await removeEntry(run, kind, entry.id), controller);
    await controller.refresh();
  }

  async function adopt(kind: LibraryKind): Promise<void> {
    if (!trusted()) return;
    const folder = await chooseFolder();
    if (folder === undefined) return;
    const run = controller.runIn(folder);
    if (run === undefined) {
      void vscode.window.showWarningMessage(INSTALL_HINT);
      return;
    }
    let outcome = await adoptEntries(run, kind);
    if (outcome.kind === "collision") {
      // Nothing was written. The user decides how to resolve every collision.
      const answer = await holder.prompts.chooseCollision(kind);
      if (answer === "terminal") {
        controller.openTerminal([kind, "adopt"], folder, `mdcompose ${kind} adopt`);
        return;
      }
      if (answer === undefined) {
        void vscode.window.showInformationMessage("Nothing was changed.");
        return;
      }
      outcome = await adoptEntries(run, kind, answer);
    }
    if (outcome.kind === "collision") {
      void vscode.window.showWarningMessage(outcome.message);
    } else {
      say(outcome, controller);
    }
    await controller.refresh();
  }

  async function reapply(): Promise<void> {
    if (!trusted()) return;
    const folder = await chooseFolder();
    if (folder === undefined) return;
    const run = controller.runIn(folder);
    const commands = controller.commandsIn(folder);
    if (run === undefined || commands === undefined) {
      void vscode.window.showWarningMessage(INSTALL_HINT);
      return;
    }
    const outcome = await reapplyProject(commands, run);
    switch (outcome.kind) {
      case "not-composed":
        void vscode.window.showInformationMessage(
          "This project has no mdcompose manifest yet. Use 'Choose Snippets and Skills for This Project' to compose it.",
        );
        break;
      case "drift": {
        const files = outcome.files.map(fileLabel).join(", ");
        const which = files === "" ? "A managed file was" : `${files} was`;
        const open = await holder.prompts.offer(
          `${which} edited by hand since mdcompose wrote it, so nothing was changed.`,
          "Open in Terminal",
        );
        if (open) controller.openTerminal(["init", "--reapply"], folder, "mdcompose reapply");
        break;
      }
      default:
        say(outcome, controller);
    }
    await controller.refresh();
  }

  function changeSelection(): Promise<void> {
    if (!trusted()) return Promise.resolve();
    return chooseFolder().then((folder) => {
      if (folder === undefined) return;
      if (!controller.isReady()) {
        void vscode.window.showWarningMessage(INSTALL_HINT);
        return;
      }
      controller.openTerminal(["init"], folder, "mdcompose init");
    });
  }

  register("mdcompose.editSnippet", (row?: Row) => edit("snippet", row));
  register("mdcompose.editSkill", (row?: Row) => edit("skill", row));
  register("mdcompose.removeSnippet", (row?: Row) => remove("snippet", row));
  register("mdcompose.removeSkill", (row?: Row) => remove("skill", row));
  register("mdcompose.adoptSnippets", () => adopt("snippet"));
  register("mdcompose.adoptSkills", () => adopt("skill"));
  register("mdcompose.reapply", () => reapply());
  register("mdcompose.changeSelection", () => changeSelection());

  // Row menu only: not offered in the command palette, because they need a row.
  register("mdcompose.copyEntryId", async (row?: Row) => {
    if (row?.entryId !== undefined) await vscode.env.clipboard.writeText(row.entryId);
  });
  register("mdcompose.revealEntry", async (row?: Row) => {
    const kind: LibraryKind = row?.contextValue === "skill" ? "skill" : "snippet";
    const entry = await chooseEntry(kind, row);
    const file = entry === undefined ? undefined : fileOf(kind, entry);
    if (file !== undefined && existsSync(file)) {
      await vscode.commands.executeCommand("revealFileInOS", vscode.Uri.file(file));
    }
  });
}
