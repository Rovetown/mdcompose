import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { MINIMUM_CLI_VERSION } from "./adapter/compat.ts";
import { isAscii } from "./adapter/support.ts";

// Guards the parts of the manifest the editor reads to draw the sidebar, so a
// rename or a missing entry is caught here instead of as a blank view.

interface Contributes {
  viewsContainers: { activitybar: { id: string; title: string; icon: string }[] };
  views: Record<string, { id: string; name: string }[]>;
  viewsWelcome: { view: string; contents: string; when: string }[];
  commands: { command: string; title: string }[];
  menus: Record<string, { command: string; when?: string }[]>;
  configuration: { properties: Record<string, { scope?: string; default?: unknown }> };
}

const root = process.cwd();
const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
  contributes: Contributes;
};
const contributes = manifest.contributes;

const VIEW_IDS = ["mdcompose.snippets", "mdcompose.skills", "mdcompose.project"];
const STATES = ["badSetting", "error", "notFound", "tooOld"];
const BUILT_IN_COMMANDS = ["workbench.action.openSettings"];

test("one Activity Bar container holds the three views", () => {
  const container = contributes.viewsContainers.activitybar[0];
  assert.equal(contributes.viewsContainers.activitybar.length, 1);
  assert.equal(container?.id, "mdcompose");
  const views = contributes.views["mdcompose"] ?? [];
  assert.deepEqual(
    views.map((view) => view.id),
    VIEW_IDS,
  );
  assert.deepEqual(
    views.map((view) => view.name),
    ["Snippets", "Skills", "Project"],
  );
});

test("the container icon exists and is a 24 by 24 image", () => {
  const icon = contributes.viewsContainers.activitybar[0]?.icon ?? "";
  const file = join(root, icon);
  assert.ok(existsSync(file), `${icon} is missing`);
  const text = readFileSync(file, "utf8");
  assert.match(text, /viewBox="0 0 24 24"/);
  assert.ok(isAscii(text));
});

test("every view has a welcome entry for every state the controller can report", () => {
  for (const view of VIEW_IDS) {
    const states = contributes.viewsWelcome
      .filter((entry) => entry.view === view)
      .map((entry) => /'(\w+)'/.exec(entry.when)?.[1])
      .sort((a, b) => String(a).localeCompare(String(b)));
    assert.deepEqual(states, STATES, `${view} welcome states`);
  }
});

test("the controller sets exactly the states the manifest has welcome text for", () => {
  const source = readFileSync(join(root, "src", "controller.ts"), "utf8");
  for (const state of [...STATES, "ready"]) {
    assert.ok(source.includes(`"${state}"`), `controller never sets ${state}`);
  }
});

test("the too-old welcome text names the version the extension really needs", () => {
  for (const entry of contributes.viewsWelcome.filter((item) => item.when.includes("'tooOld'"))) {
    assert.ok(entry.contents.includes(MINIMUM_CLI_VERSION), `${entry.view} names another version`);
  }
});

test("every button in a welcome text runs a command that exists", () => {
  const declared = new Set([
    ...contributes.commands.map((command) => command.command),
    ...BUILT_IN_COMMANDS,
  ]);
  for (const entry of contributes.viewsWelcome) {
    for (const match of entry.contents.matchAll(/\]\(command:([\w.]+)/g)) {
      assert.ok(declared.has(match[1] ?? ""), `${entry.view} runs an unknown command ${match[1]}`);
    }
  }
});

test("every contributed command has a title, and every menu item points at one", () => {
  for (const command of contributes.commands) assert.ok(command.title.length > 0);
  const declared = new Set(contributes.commands.map((command) => command.command));
  for (const items of Object.values(contributes.menus)) {
    for (const item of items) assert.ok(declared.has(item.command), item.command);
  }
});

test("the executable and timeout settings are machine-scoped, so a workspace cannot set them", () => {
  const properties = contributes.configuration.properties;
  assert.equal(properties["mdcompose.executablePath"]?.scope, "machine");
  assert.equal(properties["mdcompose.timeoutSeconds"]?.scope, "machine");
});

test("the manifest holds only plain ASCII", () => {
  const text = readFileSync(join(root, "package.json"), "utf8");
  assert.ok(isAscii(text));
});

// Commands that need a row to act on, so they are hidden from the command palette.
const ROW_ONLY = ["mdcompose.copyEntryId", "mdcompose.revealEntry"];

function sourceOf(...files: string[]): string {
  return files.map((file) => readFileSync(join(root, "src", file), "utf8")).join("\n");
}

test("every contributed command is registered in the code", () => {
  const code = sourceOf("actions.ts", "extension.ts");
  for (const command of contributes.commands) {
    assert.ok(code.includes(`"${command.command}"`), `${command.command} is never registered`);
  }
});

test("every action reachable from a button is also in the command palette", () => {
  const hidden = (contributes.menus["commandPalette"] ?? [])
    .filter((item) => item.when === "false")
    .map((item) => item.command);
  assert.deepEqual([...hidden].sort(), [...ROW_ONLY].sort());
  // The two above need a row, so they are the only commands allowed to be hidden.
  const buttons = new Set(
    Object.entries(contributes.menus)
      .filter(([location]) => location !== "commandPalette")
      .flatMap(([, items]) => items.map((item) => item.command)),
  );
  for (const command of buttons) {
    if (ROW_ONLY.includes(command)) continue;
    assert.ok(!hidden.includes(command), `${command} is a button but hidden from the palette`);
  }
});

test("buttons that change something appear only once a suitable mdcompose is ready", () => {
  const changing = [
    "mdcompose.removeSnippet",
    "mdcompose.removeSkill",
    "mdcompose.adoptSnippets",
    "mdcompose.adoptSkills",
    "mdcompose.reapply",
    "mdcompose.changeSelection",
  ];
  for (const items of Object.values(contributes.menus)) {
    for (const item of items.filter((entry) => changing.includes(entry.command))) {
      assert.match(item.when ?? "", /mdcompose\.state == 'ready'/, item.command);
    }
  }
});

test("buttons that change something are hidden in a workspace that is not trusted", () => {
  const changing = [
    "mdcompose.removeSnippet",
    "mdcompose.removeSkill",
    "mdcompose.adoptSnippets",
    "mdcompose.adoptSkills",
    "mdcompose.reapply",
    "mdcompose.changeSelection",
  ];
  for (const items of Object.values(contributes.menus)) {
    for (const item of items.filter((entry) => changing.includes(entry.command))) {
      assert.match(item.when ?? "", /isWorkspaceTrusted/, item.command);
    }
  }
});

test("the extension declares limited support for a workspace that is not trusted", () => {
  const capabilities = (
    JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
      capabilities?: { untrustedWorkspaces?: { supported?: unknown } };
    }
  ).capabilities;
  assert.equal(capabilities?.untrustedWorkspaces?.supported, "limited");
});

test("every action that changes something checks that the workspace is trusted", () => {
  const source = sourceOf("actions.ts");
  for (const name of ["remove", "adopt", "reapply", "changeSelection"]) {
    const start = source.indexOf(`function ${name}(`);
    assert.ok(start >= 0, `${name} not found`);
    const opening = source.slice(start, start + 200);
    assert.match(opening, /if \(!trusted\(\)\) return/, `${name} does not check trust`);
  }
});

test("there is no action that creates a snippet or a skill", () => {
  for (const command of contributes.commands) {
    assert.doesNotMatch(command.command, /create|new|add(?!opt)/i, command.command);
    assert.doesNotMatch(command.title, /\b(create|new|add)\b/i, command.title);
  }
});
