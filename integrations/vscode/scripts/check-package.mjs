// Builds the package, installs it into a scratch editor profile with the editor's
// own installer, and runs the editor tests against the installed copy.
//
//   CODE_EXE=<editor> MDCOMPOSE_EXE=<mdcompose> npm run check:package
//
// The ordinary editor tests load the source folder. This one loads what a user
// would get, so a file left out of the package fails here.
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const scratch = path.join(root, ".package-check");

for (const name of ["CODE_EXE", "MDCOMPOSE_EXE"]) {
  if (!process.env[name] || !existsSync(process.env[name])) {
    console.error(`Set ${name} to an existing executable.`);
    process.exit(1);
  }
}

rmSync(scratch, { recursive: true, force: true });
for (const file of readdirSync(root).filter((name) => name.endsWith(".vsix"))) {
  rmSync(path.join(root, file));
}

function run(command, args, options = {}) {
  return execFileSync(command, args, { cwd: root, encoding: "utf8", ...options });
}

// Node cannot start a .cmd file directly on Windows, so npm is run through Node.
const npmCli = process.env.npm_execpath;
run(process.execPath, [npmCli, "run", "build"], { stdio: "ignore" });
run(process.execPath, [npmCli, "run", "package"], { stdio: "ignore" });
const vsix = readdirSync(root).find((name) => name.endsWith(".vsix"));
if (vsix === undefined) throw new Error("the package was not built");

const extensions = path.join(scratch, "extensions");
const userData = path.join(scratch, "user-data");
const editor = process.env.CODE_EXE;

// The editor's own `code` command starts its executable as a plain Node process
// running cli.js. Doing the same here avoids the .cmd wrapper, which Node cannot
// start without a shell. cli.js sits next to the executable, or one folder down.
const editorDirectory = path.dirname(editor);
const cliCandidates = [
  path.join(editorDirectory, "resources", "app", "out", "cli.js"),
  ...readdirSync(editorDirectory).map((name) =>
    path.join(editorDirectory, name, "resources", "app", "out", "cli.js"),
  ),
];
const cli = cliCandidates.find((candidate) => existsSync(candidate));
if (cli === undefined) throw new Error(`could not find the editor's cli.js near ${editor}`);
const cliEnvironment = { ...process.env, ELECTRON_RUN_AS_NODE: "1", VSCODE_DEV: "" };

run(
  editor,
  [
    cli,
    "--install-extension",
    path.join(root, vsix),
    `--extensions-dir=${extensions}`,
    `--user-data-dir=${userData}`,
  ],
  { env: cliEnvironment },
);
const listed = run(
  editor,
  [
    cli,
    "--list-extensions",
    "--show-versions",
    `--extensions-dir=${extensions}`,
    `--user-data-dir=${userData}`,
  ],
  { env: cliEnvironment },
).trim();
console.log(`Installed: ${listed}`);

const installed = readdirSync(extensions).find((name) => name.includes("mdcompose"));
if (installed === undefined) throw new Error("the editor did not install the package");
const installedPath = path.join(extensions, installed);
console.log(`Testing the installed copy at ${installedPath}`);

// The editor tests load an extension from EXTENSION_DIR when it is set.
run(process.execPath, [path.join(here, "..", "test", "run.mjs")], {
  stdio: "inherit",
  env: { ...process.env, EXTENSION_DIR: installedPath },
});
rmSync(scratch, { recursive: true, force: true });
rmSync(path.join(root, vsix));
console.log("PACKAGE CHECK PASSED");
