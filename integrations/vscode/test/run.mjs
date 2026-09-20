// Starts a real editor, loads this extension into it, and runs test/suite.
//
// Set CODE_EXE to an installed editor executable to test against it. Without it
// the test tool downloads a copy of VS Code, which is a development-time download
// by the test tool, never something the extension does.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runTests } from "@vscode/test-electron";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

await runTests({
  vscodeExecutablePath: process.env.CODE_EXE,
  extensionDevelopmentPath: root,
  extensionTestsPath: path.resolve(here, "suite", "index.js"),
  launchArgs: [
    "--disable-extensions",
    "--user-data-dir",
    path.resolve(root, ".ud"),
    "--extensions-dir",
    path.resolve(root, ".ex"),
  ],
});
console.log("EDITOR TESTS PASSED");
