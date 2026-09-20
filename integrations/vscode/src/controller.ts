import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { join } from "node:path";
import * as vscode from "vscode";
import { Cache, cacheKey } from "./adapter/cache.ts";
import { createCommands, type HealthState } from "./adapter/commands.ts";
import { resolveEnvironment, type Environment } from "./adapter/environment.ts";
import { inspectPath } from "./adapter/locate.ts";
import { fromCache, refresh, type Snapshot } from "./adapter/refresh.ts";
import type { LibraryReport } from "./adapter/reports.ts";
import type { Failure, Result } from "./adapter/result.ts";
import { runCommand } from "./adapter/run.ts";
import { machineValue, timeoutMilliseconds } from "./settings.ts";
import { healthContent, libraryContent, type Content, type LibraryKind } from "./views/model.ts";
import type { Row } from "./views/model.ts";
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

  constructor(
    context: vscode.ExtensionContext,
    private readonly views: { snippets: ViewHandle; skills: ViewHandle; project: ViewHandle },
  ) {
    this.cache = new Cache(join(context.globalStorageUri.fsPath, "cache"));
    this.output = vscode.window.createOutputChannel("mdcompose");
    context.subscriptions.push(this.output);
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

  // One refresh at a time: a request made while one is running waits its turn.
  refresh(): Promise<void> {
    this.queue = this.queue.then(() => this.run());
    return this.queue;
  }

  private folder(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }

  private healthName(folder: string): string {
    return `health-${createHash("sha1").update(folder).digest("hex").slice(0, 12)}`;
  }

  private log(message: string): void {
    this.output.appendLine(message);
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
    const timeoutMs = timeoutMilliseconds(configuration.get("timeoutSeconds"));
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
    handle.provider.set(libraryContent(snapshot, kind, formatLocal));
    this.syncMessages();
  }

  private applyHealth(snapshot: Snapshot<HealthState> | null): void {
    this.views.project.provider.set(
      healthContent(snapshot, this.folder() !== undefined, formatLocal),
    );
    this.syncMessages();
  }

  // The tree view's message line mirrors the provider's content.
  private syncMessages(): void {
    this.views.snippets.view.message = this.views.snippets.provider.content.message;
    this.views.skills.view.message = this.views.skills.provider.content.message;
    this.views.project.view.message = this.views.project.provider.content.message;
  }
}
