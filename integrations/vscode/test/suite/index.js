// Runs inside the editor's extension host, so it is plain CommonJS.
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");

async function useExtension() {
  const extension = vscode.extensions.all.find(
    (candidate) => candidate.packageJSON.name === "mdcompose",
  );
  assert.ok(extension, "the extension is loaded in the test host");
  const api = await extension.activate();
  assert.strictEqual(extension.isActive, true, "the extension activates");
  return { extension, api };
}

async function setExecutable(value) {
  const configuration = vscode.workspace.getConfiguration("mdcompose");
  await configuration.update("executablePath", value, vscode.ConfigurationTarget.Global);
}

function rowNamed(rows, label) {
  const row = rows.find((candidate) => candidate.label === label);
  assert.ok(row, `no row named ${label}: ${rows.map((r) => r.label).join(", ")}`);
  return row;
}

function activePath() {
  return vscode.window.activeTextEditor?.document.uri.fsPath.toLowerCase();
}

exports.run = async function run() {
  const { extension, api } = await useExtension();

  // The container, the three views, and the commands are registered.
  const views = extension.packageJSON.contributes.views.mdcompose.map((view) => view.id);
  assert.deepStrictEqual(views, ["mdcompose.snippets", "mdcompose.skills", "mdcompose.project"]);
  const commands = await vscode.commands.getCommands(true);
  for (const command of extension.packageJSON.contributes.commands.map((c) => c.command)) {
    assert.ok(commands.includes(command), `${command} is registered`);
  }

  // A path that does not run is reported, and the views are left empty so the
  // welcome text shows. It does not fall back to the search path.
  const missing = path.join(os.tmpdir(), "no-such-dir", "mdcompose.exe");
  await setExecutable(missing);
  await api.refresh();
  const unusable = api.state();
  assert.strictEqual(unusable.environment, "setting-unusable");
  assert.deepStrictEqual(unusable.snippets.rows, []);
  assert.strictEqual(unusable.snippets.message, undefined);

  // With no setting and nothing on the search path, mdcompose is not found.
  await setExecutable("");
  const originalPath = process.env.PATH;
  process.env.PATH = fs.mkdtempSync(path.join(os.tmpdir(), "empty-path-"));
  try {
    await api.refresh();
    assert.strictEqual(api.state().environment, "not-found");
  } finally {
    process.env.PATH = originalPath;
  }

  const exe = process.env.MDCOMPOSE_TEST_EXE;
  if (!exe) {
    console.log("MDCOMPOSE_EXE not set: skipped the end-to-end checks");
    return;
  }

  // The end-to-end checks run the real command line against a scratch
  // configuration directory and a composed scratch project, both built by
  // test/run.mjs. Dialogs are answered by the test.
  const configDirectory = process.env.MDCOMPOSE_CONFIG_DIR;
  const snippetsDirectory = path.join(configDirectory, "snippets");
  const project = vscode.workspace.workspaceFolders[0].uri.fsPath;
  const agents = path.join(project, "AGENTS.md");
  const commitFile = path.join(snippetsDirectory, "commit-style.md");

  await setExecutable(exe);
  await vscode.commands.executeCommand("mdcompose.refresh");
  let state = api.state();
  assert.strictEqual(state.environment, "ready");
  assert.strictEqual(state.executable, exe);

  const snippetTitles = state.snippets.rows.map((row) => row.label).sort();
  assert.deepStrictEqual(snippetTitles, ["Commit style", "Python style"]);
  assert.strictEqual(rowNamed(state.snippets.rows, "Commit style").description, "git, conventions");
  assert.strictEqual(state.snippets.message, undefined);
  assert.deepStrictEqual(
    state.skills.rows.map((row) => row.label),
    ["Code review"],
  );

  // The scratch project was composed, so its files are listed.
  const projectLabels = state.project.rows.map((row) => row.label);
  assert.ok(projectLabels.includes("AGENTS.md"), projectLabels.join(", "));
  assert.ok(projectLabels.includes("CLAUDE.md"), projectLabels.join(", "));
  assert.ok(!projectLabels.includes("Not composed yet"));

  // Editing a snippet opens its file, from the row and from the command palette.
  await vscode.commands.executeCommand(
    "mdcompose.editSnippet",
    rowNamed(state.snippets.rows, "Commit style"),
  );
  assert.strictEqual(activePath(), commitFile.toLowerCase());
  api.setPrompts({ pickEntry: async () => "python-style" });
  await vscode.commands.executeCommand("mdcompose.editSnippet");
  assert.strictEqual(activePath(), path.join(snippetsDirectory, "python-style.md").toLowerCase());
  await vscode.commands.executeCommand(
    "mdcompose.editSkill",
    rowNamed(state.skills.rows, "Code review"),
  );
  assert.strictEqual(
    activePath(),
    path.join(configDirectory, "skills", "code-review.md").toLowerCase(),
  );

  // Removing asks first. Declining changes nothing; confirming removes it.
  const asked = [];
  api.setPrompts({
    confirmRemove: async (kind, title, id) => {
      asked.push([kind, title, id]);
      return false;
    },
  });
  await vscode.commands.executeCommand(
    "mdcompose.removeSnippet",
    rowNamed(api.state().snippets.rows, "Python style"),
  );
  assert.deepStrictEqual(asked, [["snippet", "Python style", "python-style"]]);
  assert.ok(fs.existsSync(path.join(snippetsDirectory, "python-style.md")), "declined: kept");

  api.setPrompts({ confirmRemove: async () => true });
  await vscode.commands.executeCommand(
    "mdcompose.removeSnippet",
    rowNamed(api.state().snippets.rows, "Python style"),
  );
  assert.ok(!fs.existsSync(path.join(snippetsDirectory, "python-style.md")), "confirmed: removed");
  assert.deepStrictEqual(
    api.state().snippets.rows.map((row) => row.label),
    ["Commit style"],
  );

  // Adopting brings back what the project's manifest embeds. The manifest keeps
  // only the body, so the adopted snippet has no title and is listed by its id.
  await vscode.commands.executeCommand("mdcompose.adoptSnippets");
  assert.deepStrictEqual(
    api
      .state()
      .snippets.rows.map((row) => row.label)
      .sort(),
    ["Commit style", "python-style"],
  );

  // A collision is put to the user, and nothing changes until they answer.
  fs.writeFileSync(commitFile, "---\ntitle: Commit style\n---\n\nDifferent text.\n");
  let questions = 0;
  api.setPrompts({
    chooseCollision: async () => {
      questions += 1;
      return undefined;
    },
  });
  await vscode.commands.executeCommand("mdcompose.adoptSnippets");
  assert.strictEqual(questions, 1);
  assert.match(fs.readFileSync(commitFile, "utf8"), /Different text/, "no answer: unchanged");

  api.setPrompts({ chooseCollision: async () => "keep" });
  await vscode.commands.executeCommand("mdcompose.adoptSnippets");
  assert.match(fs.readFileSync(commitFile, "utf8"), /Different text/, "keep: unchanged");

  api.setPrompts({ chooseCollision: async () => "overwrite" });
  await vscode.commands.executeCommand("mdcompose.adoptSnippets");
  const replaced = fs.readFileSync(commitFile, "utf8");
  assert.match(replaced, /Prefer small commits\./, "overwrite: the project's copy is back");
  assert.doesNotMatch(replaced, /Different text/, "overwrite: the library copy is gone");

  // Reapplying a clean project just works. Hand edits are reported and kept.
  await vscode.commands.executeCommand("mdcompose.reapply");
  const original = fs.readFileSync(agents, "utf8");
  fs.writeFileSync(agents, original.replace("Prefer small commits.", "Hand edited."));
  const offers = [];
  api.setPrompts({
    offer: async (message, button) => {
      offers.push([message, button]);
      return false;
    },
  });
  await vscode.commands.executeCommand("mdcompose.reapply");
  assert.strictEqual(offers.length, 1);
  assert.match(offers[0][0], /AGENTS\.md was edited by hand/);
  assert.match(offers[0][0], /nothing was changed/);
  assert.strictEqual(offers[0][1], "Open in Terminal");
  assert.match(fs.readFileSync(agents, "utf8"), /Hand edited\./, "hand edits are kept");
  await vscode.commands.executeCommand("mdcompose.refresh");
  assert.strictEqual(rowNamed(api.state().project.rows, "AGENTS.md").description, "drifted");
  fs.writeFileSync(agents, original);

  // Changing the selection opens the command line's own picker in a terminal.
  await vscode.commands.executeCommand("mdcompose.changeSelection");
  const terminal = vscode.window.terminals.find((candidate) => candidate.name === "mdcompose init");
  assert.ok(terminal, "a terminal running mdcompose init was opened");
  terminal.dispose();

  // A workspace cannot name the program the extension runs: try, and confirm the
  // user's setting is still the one in use.
  const configuration = vscode.workspace.getConfiguration("mdcompose");
  try {
    await configuration.update(
      "executablePath",
      path.join(os.tmpdir(), "evil", "mdcompose.exe"),
      vscode.ConfigurationTarget.Workspace,
    );
  } catch {
    // The editor refuses a workspace value for a machine-scoped setting. Either
    // way the next check is what matters.
  }
  await api.refresh();
  state = api.state();
  assert.strictEqual(state.environment, "ready");
  assert.strictEqual(state.executable, exe);

  await setExecutable(undefined);
};
