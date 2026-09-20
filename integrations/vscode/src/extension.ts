import * as vscode from "vscode";
import { Controller, type ViewState } from "./controller.ts";
import type { Row } from "./views/model.ts";
import { RowsProvider } from "./views/provider.ts";

// What the editor tests can ask a running extension. Nothing else depends on it.
export interface ExtensionApi {
  refresh: () => Promise<void>;
  state: () => ViewState;
}

function createView(id: string): { provider: RowsProvider; view: vscode.TreeView<Row> } {
  const provider = new RowsProvider();
  const view = vscode.window.createTreeView<Row>(id, { treeDataProvider: provider });
  return { provider, view };
}

export function activate(context: vscode.ExtensionContext): ExtensionApi {
  const views = {
    snippets: createView("mdcompose.snippets"),
    skills: createView("mdcompose.skills"),
    project: createView("mdcompose.project"),
  };
  for (const handle of Object.values(views)) {
    context.subscriptions.push(handle.view, { dispose: () => handle.provider.dispose() });
  }

  const controller = new Controller(context, views);
  context.subscriptions.push(
    vscode.commands.registerCommand("mdcompose.refresh", () => controller.refresh()),
    vscode.commands.registerCommand("mdcompose.showOutput", () => controller.showOutput()),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("mdcompose")) void controller.refresh();
    }),
    vscode.workspace.onDidChangeWorkspaceFolders(() => void controller.refresh()),
  );

  void controller.start();
  return { refresh: () => controller.refresh(), state: () => controller.state() };
}

export function deactivate(): void {}
