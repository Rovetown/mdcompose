// Starts a real editor, loads this extension into it, and runs test/suite.
//
// Set CODE_EXE to an installed editor executable to test against it. Without it
// the test tool downloads a copy of VS Code, which is a development-time download
// by the test tool, never something the extension does.
//
// Set MDCOMPOSE_EXE to an mdcompose executable to also run the end-to-end checks.
// They run against a scratch home and configuration directory built here, never
// the real ones: the editor is started with the environment variables that move
// them, so nothing on the real machine is read or written.
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runTests } from "@vscode/test-electron";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const scratch = path.resolve(root, ".scratch");

function writeSample(directory, name, text) {
  mkdirSync(directory, { recursive: true });
  writeFileSync(path.join(directory, name), text, "utf8");
}

const env = {};
const launchArgs = [
  // The tests must not wait on the workspace trust prompt.
  "--disable-workspace-trust",
  "--disable-extensions",
  "--user-data-dir",
  path.resolve(root, ".ud"),
  "--extensions-dir",
  path.resolve(root, ".ex"),
];

if (process.env.MDCOMPOSE_EXE) {
  rmSync(scratch, { recursive: true, force: true });
  const config = path.join(scratch, "config");
  const home = path.join(scratch, "home");
  const project = path.join(scratch, "project");
  mkdirSync(home, { recursive: true });
  mkdirSync(project, { recursive: true });
  writeSample(
    path.join(config, "snippets"),
    "commit-style.md",
    "---\ntitle: Commit style\ndescription: How commits are written here\ntags: [git, conventions]\ncategory: conventions\n---\n\nPrefer small commits.\n",
  );
  writeSample(
    path.join(config, "snippets"),
    "python-style.md",
    "---\ntitle: Python style\ntags: [python]\ncategory: languages\n---\n\nUse pathlib.\n",
  );
  writeSample(
    path.join(config, "skills"),
    "code-review.md",
    "---\ntitle: Code review\ndescription: How we review code here\ntags: [review]\ncategory: process\n---\n\nReview for correctness first.\n",
  );
  // Compose the scratch project with the real command line, so the actions have a
  // manifest to work from.
  execFileSync(
    path.resolve(process.env.MDCOMPOSE_EXE),
    ["init", "--yes", "--mode", "copy", "--snippets", "commit-style,python-style"],
    {
      cwd: project,
      stdio: "ignore",
      env: { ...process.env, MDCOMPOSE_CONFIG_DIR: config, USERPROFILE: home, HOME: home },
    },
  );
  Object.assign(env, {
    MDCOMPOSE_CONFIG_DIR: config,
    USERPROFILE: home,
    HOME: home,
    MDCOMPOSE_TEST_EXE: path.resolve(process.env.MDCOMPOSE_EXE),
  });
  // Opening a folder makes it the workspace the Project view reports on.
  launchArgs.unshift(project);
}

await runTests({
  vscodeExecutablePath: process.env.CODE_EXE,
  extensionDevelopmentPath: root,
  extensionTestsPath: path.resolve(here, "suite", "index.js"),
  extensionTestsEnv: env,
  launchArgs,
});
console.log("EDITOR TESTS PASSED");
