import * as vscode from "vscode";
import type { Content, Row } from "./model.ts";

// Turns the rows the view model produced into tree items. It holds no logic of
// its own, so what it shows is decided, and tested, in model.ts.
export class RowsProvider implements vscode.TreeDataProvider<Row> {
  private current: Content = { rows: [], message: undefined };
  private readonly changed = new vscode.EventEmitter<undefined>();
  readonly onDidChangeTreeData = this.changed.event;

  set(content: Content): void {
    this.current = content;
    this.changed.fire(undefined);
  }

  get content(): Content {
    return this.current;
  }

  getChildren(element?: Row): Row[] {
    return element === undefined ? this.current.rows : [];
  }

  getTreeItem(row: Row): vscode.TreeItem {
    const item = new vscode.TreeItem(row.label, vscode.TreeItemCollapsibleState.None);
    item.id = row.id;
    item.description = row.description;
    item.tooltip = row.tooltip;
    item.iconPath = new vscode.ThemeIcon(row.icon);
    item.contextValue = row.contextValue;
    return item;
  }

  dispose(): void {
    this.changed.dispose();
  }
}
