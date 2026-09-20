# mdcompose for VS Code

A sidebar for VS Code, VSCodium, and Cursor that shows your mdcompose snippet and
skill libraries and your project's composition state, and runs the matching
`mdcompose` commands. It is a graphical layer over the command line: it runs
`mdcompose` in the background and shows the result. It offers only what the
command line offers.

This is an early scaffold. It builds, packages, and loads in the editor, and does
nothing else yet. The views and commands arrive in the next tasks of the
`vscode-extension` change.

## Requirements

The `mdcompose` command line must be installed. The extension never installs,
downloads, or updates it, and it makes no network requests and sends no telemetry.

## Development

The toolchain is npm (with Node 22 or newer) and the lockfile is
`package-lock.json`. Install with `npm ci`, the same command CI uses, so a local
install is exactly what CI gets.

    npm ci                 install exactly what package-lock.json records
    npm run build          bundle src/extension.ts to dist/extension.js
    npm run typecheck      type-check with tsc
    npm run lint           oxlint, type-aware
    npm run format         oxfmt, check only (format:write fixes)
    npm run test           bundle the unit tests with esbuild, run them with Node
    npm run test:editor    load the extension into a real editor and test it
    npm run package        build the .vsix package
    npm run icon           re-render media/icon.png from media/icon-source.svg

The unit tests are bundled first, then run by Node's built-in test runner, so they
work on any Node 22 or newer build, including distribution builds of Node that
cannot run TypeScript directly (the WSL Ubuntu package is one).

`test:editor` starts a real editor. Set `CODE_EXE` to an installed editor
executable to use it; otherwise the test tool downloads VS Code.

### Using Bun locally

Bun is optional and only a convenience. The scripts contain no Bun-specific
commands and the source uses no Bun-only API, so `bun run <script>` works in place
of `npm run <script>` and starts a little faster (about 50 to 200 ms less per
script on Windows). Keep installing with `npm ci`: `bun install` in this project
writes its own `bun.lock` (git ignores it) and resolved 3 of 348 packages to
different versions than `package-lock.json` in a test, so a Bun install is not the
tree CI gets. On a fresh install npm was also 4 to 6 times faster than Bun on
Windows (6.5 s against 40 s with an empty cache).

## Try it

Open `integrations/vscode` in VS Code and press F5. A second window opens with
the extension loaded. Click the mdcompose icon in its Activity Bar to see the
Snippets, Skills, and Project views. Everything the views run is read-only (the
list and health commands), so trying it against your real library changes
nothing. If `mdcompose` is not on your search path, set `mdcompose.executablePath`
in your user settings; a workspace cannot set it.

## Try it in a sandbox

To try every action without touching your real library or projects:

    npm run build
    MDCOMPOSE_EXE=<path to mdcompose> npm run sandbox

This builds `.sandbox/` (ignored by git, safe to delete) with a scratch mdcompose
library, a scratch home, and two projects, `alpha` (composed) and `beta` (not
composed), then opens a new editor window on both with the extension loaded. That
window uses its own editor profile and the scratch environment, so `Adopt`,
`Remove`, and `Reapply` only ever change files under `.sandbox/`. Add `--trusted`
to skip the workspace trust prompt, or leave it off and choose "No" to see
Restricted Mode: the views still read, and the buttons that change files are
hidden and the commands refuse.

The editor tests never use your real library. `test/run.mjs` builds a scratch
home and configuration directory and starts the editor with the environment
variables that move them.

## Supported editors

One package targets VS Code, VSCodium, and Cursor. The minimum editor version is
`^1.90.0`, and the editor API types are pinned to 1.90.0, because the packaging
tool refuses types newer than the minimum. That floor is provisional: it has been
checked only against VS Code 1.134, and must be lowered or confirmed once VSCodium
and Cursor are installed and their engine versions are known.

## Platforms

Built and tested on Windows only so far. macOS and Linux are untested.

## Publisher

The publisher id in `package.json` is a placeholder (`publisher-tbd`) until the
maintainer registers one. Publishing is done by hand.
