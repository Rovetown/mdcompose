import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { basename, join } from "node:path";
import * as vscode from "vscode";
import type { Run } from "./adapter/actions.ts";
import { Cache, cacheKey } from "./adapter/cache.ts";
import { createCommands, type Commands, type HealthState } from "./adapter/commands.ts";
import { resolveEnvironment, type Environment } from "./adapter/environment.ts";
import { inspectPath } from "./adapter/locate.ts";
import { fromCache, refresh, type Snapshot } from "./adapter/refresh.ts";
import type { LibraryReport } from "./adapter/reports.ts";
import type { Failure, Result } from "./adapter/result.ts";
import { runCommand } from "./adapter/run.ts";
import { machineValue, timeoutMilliseconds } from "./settings.ts";
import {
  healthContent,
  libraryContent,
  type Content,
  type LibraryKind,
  type Row,
} from "./views/model.ts";
import { withLibraryHints, withProjectHints } from "./views/hints.ts";
import type { RowsProvider } from "./views/provider.ts";
import { formatLocal } from "./views/time.ts";

// What the tests can ask the running extension. Not part of any public contract.
export interface ViewState {
  environment: Environment["kind"] | "unresolved";
  // The program the extension is using, when it found one.
  executable: string | undefined;
  snippets: Content;
  skills: Content;
  project: Content;
}

export interface ViewHandle {
  provider: RowsProvider;
  view: vscode.TreeView<Row>;
}

// Which welcome text the views show. The manifest has one entry per value.
const STATE_KEY = "mdcompose.state";
const ENVIRONMENT_CACHE = "environment";
const ENVIRONMENT_KEY = "1";

function welcomeState(environment: Environment): string {
  switch (environment.kind) {
    case "ready":
      return "ready";
    case "not-found":
      return "notFound";
    case "setting-unusable":
      return "badSetting";
    case "too-old":
      return "tooOld";
    case "unreadable":
      return "error";
  }
}

interface KnownEnvironment {
  executable: string;
  version: string;
}

// Runs the command line and keeps the three views up to date. All the rules live
// in the adapter and the view model; this only connects them to the editor.
export class Controller {
  private readonly cache: Cache;
  private readonly output: vscode.OutputChannel;
  private queue: Promise<void> = Promise.resolve();
  private environment: Environment | undefined;
  private warnedNewer = false;
  private chosenFolder: string | undefined;
  private readonly libraries = new Map<LibraryKind, LibraryReport>();
  private readonly ownTerminals = new WeakSet<vscode.Terminal>();
  private readonly views: { snippets: ViewHandle; skills: ViewHandle; project: ViewHandle };

  constructor(
    context: vscode.ExtensionContext,
    views: { snippets: ViewHandle; skills: ViewHandle; project: ViewHandle },
  ) {
    this.views = views;
    this.cache = new Cache(join(context.globalStorageUri.fsPath, "cache"));
    this.output = vscode.window.createOutputChannel("mdcompose");
    context.subscriptions.push(
      this.output,
      // A terminal the extension opened may have changed the libraries or the
      // project, so its closing triggers a refresh.
      vscode.window.onDidCloseTerminal((terminal) => {
        if (this.ownTerminals.has(terminal)) void this.refresh();
      }),
    );
  }

  state(): ViewState {
    return {
      environment: this.environment?.kind ?? "unresolved",
      executable: this.environment?.kind === "ready" ? this.environment.executable : undefined,
      snippets: this.views.snippets.provider.content,
      skills: this.views.skills.provider.content,
      project: this.views.project.provider.content,
    };
  }

  showOutput(): void {
    this.output.show(true);
  }

  log(message: string): void {
    this.output.appendLine(message);
  }

  // The last library the command line reported, from a fresh read or the cache.
  library(kind: LibraryKind): LibraryReport | undefined {
    return this.libraries.get(kind);
  }

  // Whether a suitable command line was found. The actions need one.
  isReady(): boolean {
    return this.environment?.kind === "ready";
  }

  // A function that runs the command line in `cwd`, or undefined when it is not ready.
  runIn(cwd: string): Run | undefined {
    if (this.environment?.kind !== "ready") return undefined;
    const executable = this.environment.executable;
    const timeoutMs = this.timeout();
    return (args) => runCommand({ executable, args, cwd, timeoutMs });
  }

  commandsIn(cwd: string): Commands | undefined {
    const run = this.runIn(cwd);
    return run === undefined ? undefined : createCommands(run);
  }

  // Runs the command line in a real terminal, so its own prompts work.
  openTerminal(args: string[], cwd: string, name: string): void {
    if (this.environment?.kind !== "ready") return;
    const terminal = vscode.window.createTerminal({
      name,
      cwd,
      shellPath: this.environment.executable,
      shellArgs: args,
    });
    this.ownTerminals.add(terminal);
    terminal.show();
  }

  // The folder the Project view reports on. In a window with several folders the
  // user chooses; otherwise it is the only one.
  folder(): string | undefined {
    const folders = vscode.workspace.workspaceFolders ?? [];
    const chosen = folders.find((folder) => folder.uri.fsPath === this.chosenFolder);
    return (chosen ?? folders[0])?.uri.fsPath;
  }

  setFolder(folder: string): Promise<void> {
    if (this.chosenFolder === folder) return Promise.resolve();
    this.chosenFolder = folder;
    return this.refresh();
  }

  // Shows a loading line, then whatever was cached last time at once, before
  // anything is run, and then refreshes.
  start(): Promise<void> {
    for (const handle of [this.views.snippets, this.views.skills, this.views.project]) {
      handle.provider.set({ rows: [], message: "Loading." });
    }
    this.syncMessages();
    this.showCached();
    return this.refresh();
  }

  // One refresh at a time: a request made while one is running waits its turn.
  refresh(): Promise<void> {
    this.queue = this.queue.then(() => this.run());
    return this.queue;
  }

  private timeout(): number {
    return timeoutMilliseconds(
      vscode.workspace.getConfiguration("mdcompose").get("timeoutSeconds"),
    );
  }

  private showCached(): void {
    const known = this.cache.load<KnownEnvironment>(ENVIRONMENT_CACHE, ENVIRONMENT_KEY);
    if (known === null) return;
    const { executable, version } = known.value;
    const libraryKey = cacheKey(version, executable);
    this.applyLibrary("snippet", fromCache<LibraryReport>(this.cache, "snippets", libraryKey));
    this.applyLibrary("skill", fromCache<LibraryReport>(this.cache, "skills", libraryKey));
    const folder = this.folder();
    if (folder !== undefined) {
      const key = cacheKey(version, `${executable}|${folder}`);
      this.applyHealth(fromCache<HealthState>(this.cache, this.healthName(folder), key));
    } else {
      this.applyHealth(null);
    }
  }

  private healthName(folder: string): string {
    return `health-${createHash("sha1").update(folder).digest("hex").slice(0, 12)}`;
  }

  private async run(): Promise<void> {
    try {
      await this.resolveAndRefresh();
    } catch (error) {
      this.log(`Unexpected error: ${String(error)}`);
    }
  }

  private async resolveAndRefresh(): Promise<void> {
    const configuration = vscode.workspace.getConfiguration("mdcompose");
    const setting = machineValue(configuration.inspect<string>("executablePath"));
    const timeoutMs = this.timeout();
    const folder = this.folder();
    const cwd = folder ?? homedir();

    const environment = await resolveEnvironment({
      setting,
      env: process.env,
      platform: process.platform,
      inspect: (path) => inspectPath(path),
      runVersion: (executable) => runCommand({ executable, args: ["--version"], cwd, timeoutMs }),
    });
    this.environment = environment;
    await vscode.commands.executeCommand("setContext", STATE_KEY, welcomeState(environment));
    if (environment.kind !== "ready") {
      this.log(environment.message);
      this.views.snippets.provider.set({ rows: [], message: undefined });
      this.views.skills.provider.set({ rows: [], message: undefined });
      this.views.project.provider.set({ rows: [], message: undefined });
      this.syncMessages();
      return;
    }
    if (environment.newerThanTested && !this.warnedNewer) {
      this.warnedNewer = true;
      const text = `mdcompose ${environment.version} is newer than the version this extension was tested against.`;
      this.log(text);
      void vscode.window.showWarningMessage(text);
    }

    const { executable, version } = environment;
    const commands = createCommands((args) => runCommand({ executable, args, cwd, timeoutMs }));
    const libraryKey = cacheKey(version, executable);
    const now = (): Date => new Date();

    const snippets = await refresh<LibraryReport>({
      cache: this.cache,
      name: "snippets",
      key: libraryKey,
      now,
      read: () => this.logged("snippet list", commands.snippetList()),
    });
    this.applyLibrary("snippet", snippets);
    const skills = await refresh<LibraryReport>({
      cache: this.cache,
      name: "skills",
      key: libraryKey,
      now,
      read: () => this.logged("skill list", commands.skillList()),
    });
    this.applyLibrary("skill", skills);

    if (folder === undefined) {
      this.applyHealth(null);
    } else {
      const health = await refresh<HealthState>({
        cache: this.cache,
        name: this.healthName(folder),
        key: cacheKey(version, `${executable}|${folder}`),
        now,
        read: () => this.logged("doctor", commands.health()),
      });
      this.applyHealth(health);
    }
    this.cache.save<KnownEnvironment>(ENVIRONMENT_CACHE, {
      savedAt: now().toISOString(),
      key: ENVIRONMENT_KEY,
      value: { executable, version },
    });
  }

  private async logged<T>(
    what: string,
    pending: Promise<Result<T, Failure>>,
  ): Promise<Result<T, Failure>> {
    const result = await pending;
    if (!result.ok) this.log(`${what}: ${result.error.message}`);
    return result;
  }

  private applyLibrary(kind: LibraryKind, snapshot: Snapshot<LibraryReport> | null): void {
    const handle = kind === "snippet" ? this.views.snippets : this.views.skills;
    handle.provider.set(withLibraryHints(libraryContent(snapshot, kind, formatLocal), kind));
    if (snapshot !== null && snapshot.state !== "unavailable") {
      this.libraries.set(kind, snapshot.value);
    }
    this.syncMessages();
  }

  private applyHealth(snapshot: Snapshot<HealthState> | null): void {
    this.views.project.provider.set(
      withProjectHints(healthContent(snapshot, this.folder() !== undefined, formatLocal)),
    );
    this.syncMessages();
  }

  // The tree view's message line mirrors the provider's content, and the Project
  // view names its folder when the window has several.
  private syncMessages(): void {
    this.views.snippets.view.message = this.views.snippets.provider.content.message;
    this.views.skills.view.message = this.views.skills.provider.content.message;
    this.views.project.view.message = this.views.project.provider.content.message;
    const folders = vscode.workspace.workspaceFolders ?? [];
    const folder = this.folder();
    this.views.project.view.description =
      folders.length > 1 && folder !== undefined ? basename(folder) : undefined;
  }
}
