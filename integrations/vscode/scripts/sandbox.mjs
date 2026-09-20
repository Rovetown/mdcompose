// Opens a separate editor window with the extension loaded, against a scratch
// home, a scratch mdcompose library, and two scratch projects, so every action can
// be tried by hand without touching your real library or projects.
//
//   npm run build
//   MDCOMPOSE_EXE=<path to mdcompose> node scripts/sandbox.mjs [--no-launch] [--trusted]
//
// Everything is built under .sandbox/, which is ignored by git and safe to delete.
// --no-launch only builds the sandbox and prints how to open it.
// --trusted skips the workspace trust prompt; leave it off to try Restricted Mode.
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const sandbox = path.join(root, ".sandbox");
const flags = new Set(process.argv.slice(2));

function findMdcompose() {
  if (process.env.MDCOMPOSE_EXE) return path.resolve(process.env.MDCOMPOSE_EXE);
  const repo = path.resolve(root, "..", "..");
  const candidates = [
    path.join(repo, ".venv", "Scripts", "mdcompose.exe"),
    path.join(repo, ".venv", "bin", "mdcompose"),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function findEditor() {
  if (process.env.CODE_EXE) return { command: process.env.CODE_EXE, shell: false };
  if (process.platform === "win32" && process.env.LOCALAPPDATA) {
    const installed = path.join(
      process.env.LOCALAPPDATA,
      "Programs",
      "Microsoft VS Code",
      "Code.exe",
    );
    if (existsSync(installed)) return { command: installed, shell: false };
  }
  // The `code` command is a script on Windows, which needs a shell to start.
  return { command: "code", shell: process.platform === "win32" };
}

const mdcompose = findMdcompose();
if (mdcompose === undefined || !existsSync(mdcompose)) {
  console.error("Set MDCOMPOSE_EXE to the path of the mdcompose executable.");
  process.exit(1);
}
if (!existsSync(path.join(root, "dist", "extension.js"))) {
  console.error("Build first: npm run build.");
  process.exit(1);
}

rmSync(sandbox, { recursive: true, force: true });
const config = path.join(sandbox, "config");
const home = path.join(sandbox, "home");
const alpha = path.join(sandbox, "projects", "alpha");
const beta = path.join(sandbox, "projects", "beta");
const userData = path.join(sandbox, "editor-user-data");
for (const directory of [home, alpha, beta, path.join(userData, "User")]) {
  mkdirSync(directory, { recursive: true });
}

function write(directory, name, text) {
  mkdirSync(directory, { recursive: true });
  writeFileSync(path.join(directory, name), text, "utf8");
}

write(
  path.join(config, "snippets"),
  "commit-style.md",
  "---\ntitle: Commit style\ndescription: How commits are written here\ntags: [git, conventions]\ncategory: conventions\n---\n\nPrefer small commits.\n",
);
write(
  path.join(config, "snippets"),
  "python-style.md",
  "---\ntitle: Python style\ntags: [python]\ncategory: languages\n---\n\nUse pathlib.\n",
);
write(
  path.join(config, "snippets"),
  "testing.md",
  "---\ntitle: Testing\ntags: [tests]\n---\n\nWrite the test first.\n",
);
write(
  path.join(config, "skills"),
  "code-review.md",
  "---\ntitle: Code review\ndescription: How we review code here\ntags: [review]\ncategory: process\n---\n\nReview for correctness first.\n",
);

// The two projects: alpha is composed with the real command line, beta is not.
const scratchEnvironment = {
  ...process.env,
  MDCOMPOSE_CONFIG_DIR: config,
  USERPROFILE: home,
  HOME: home,
};
execFileSync(
  mdcompose,
  ["init", "--yes", "--mode", "copy", "--snippets", "commit-style,python-style"],
  { cwd: alpha, stdio: "ignore", env: scratchEnvironment },
);

// Two folders in one window, to try the folder choice.
const workspaceFile = path.join(sandbox, "two-folders.code-workspace");
writeFileSync(
  workspaceFile,
  JSON.stringify({ folders: [{ path: "projects/alpha" }, { path: "projects/beta" }] }, null, 2),
  "utf8",
);

// A fresh editor profile that already points at the scratch command line.
writeFileSync(
  path.join(userData, "User", "settings.json"),
  JSON.stringify(
    {
      "mdcompose.executablePath": mdcompose,
      "workbench.startupEditor": "none",
      "telemetry.telemetryLevel": "off",
    },
    null,
    2,
  ),
  "utf8",
);

const args = [
  `--extensionDevelopmentPath=${root}`,
  `--user-data-dir=${userData}`,
  `--extensions-dir=${path.join(sandbox, "editor-extensions")}`,
  "--new-window",
  "--disable-extensions",
  ...(flags.has("--trusted") ? ["--disable-workspace-trust"] : []),
  workspaceFile,
];

console.log(`Sandbox built in ${sandbox}`);
console.log(`  mdcompose library  ${config}`);
console.log(`  project alpha      ${alpha}  (composed)`);
console.log(`  project beta       ${beta}  (not composed)`);
console.log("");
console.log("Things to try:");
console.log("  Multi-folder   Copy Into Library, Recompose, and Choose Snippets ask which folder.");
console.log(
  "  Drift          Edit alpha/AGENTS.md by hand, then Reapply: it stops and offers a terminal.",
);
console.log(
  "  Collision      Change a snippet in the library, then Adopt: it asks keep / replace / terminal.",
);
console.log(
  "  Terminal       Choose Open in Terminal or Decide in Terminal to reach the command line's own prompts.",
);
console.log(
  "  Trust          Start without --trusted, choose No at the trust prompt, and see Restricted Mode.",
);

if (flags.has("--no-launch")) {
  const { command } = findEditor();
  console.log("");
  console.log("Open it with:");
  console.log(`  ${command} ${args.map((arg) => JSON.stringify(arg)).join(" ")}`);
  console.log("with MDCOMPOSE_CONFIG_DIR, USERPROFILE, and HOME set to the sandbox paths.");
} else {
  const editor = findEditor();
  const child = spawn(editor.command, args, {
    env: scratchEnvironment,
    detached: true,
    stdio: "ignore",
    shell: editor.shell,
    // No windowsHide here, unlike the adapter: that option hides the program's
    // window on Windows, and this program is a window the user wants to see.
  });
  child.unref();
  console.log("");
  console.log("Opened a new editor window.");
}
