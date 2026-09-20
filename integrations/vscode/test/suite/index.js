// Runs inside the editor's extension host, so it is plain CommonJS.
const assert = require("node:assert");
const { mkdtempSync } = require("node:fs");
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

exports.run = async function run() {
  const { extension, api } = await useExtension();

  // The container, the three views, and the commands are registered.
  const views = extension.packageJSON.contributes.views.mdcompose.map((view) => view.id);
  assert.deepStrictEqual(views, ["mdcompose.snippets", "mdcompose.skills", "mdcompose.project"]);
  const commands = await vscode.commands.getCommands(true);
  assert.ok(commands.includes("mdcompose.refresh"), "refresh command exists");
  assert.ok(commands.includes("mdcompose.showOutput"), "show details command exists");

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
  process.env.PATH = mkdtempSync(path.join(os.tmpdir(), "empty-path-"));
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
  // configuration directory, set up by test/run.mjs.
  await setExecutable(exe);
  await vscode.commands.executeCommand("mdcompose.refresh");
  const ready = api.state();
  assert.strictEqual(ready.environment, "ready");
  assert.strictEqual(ready.executable, exe);

  const snippetTitles = ready.snippets.rows.map((row) => row.label).sort();
  assert.deepStrictEqual(snippetTitles, ["Commit style", "Python style"]);
  const commit = ready.snippets.rows.find((row) => row.label === "Commit style");
  assert.strictEqual(commit.description, "git, conventions");
  assert.strictEqual(ready.snippets.message, undefined);

  assert.deepStrictEqual(
    ready.skills.rows.map((row) => row.label),
    ["Code review"],
  );

  // The scratch project was never composed, so it says so.
  const project = ready.project.rows.map((row) => row.label);
  assert.ok(project[0] === "Healthy" || project[0] === "Needs attention", project.join(", "));
  assert.ok(project.includes("Not composed yet"), project.join(", "));

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
  const afterWorkspaceAttempt = api.state();
  assert.strictEqual(afterWorkspaceAttempt.environment, "ready");
  assert.strictEqual(afterWorkspaceAttempt.executable, exe);

  await setExecutable(undefined);
};
