# Developing the mdcompose extension

The listing page (what users see on the marketplaces) is `README.md`. This file is
for people working on the extension, and it is not part of the package.

The design and the reasoning are in the OpenSpec changes `integrations-foundation`
and `vscode-extension`, and the decisions log in the repository's `TODO.md`. The
shared rules for every integration are in `../README.md`.

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

## Versions

Recorded on 2026-09-20 and checked against what is installed.

| What | Version |
| ---- | ------- |
| Minimum editor (`engines.vscode`) | `^1.90.0` |
| Editor API types (`@types/vscode`) | `1.90.0`, never newer than the minimum or the packager refuses |
| mdcompose command line, lowest supported | 0.3.0 (`src/adapter/compat.ts`) |
| mdcompose command line, highest tested | 0.3.0 |
| Node (for the tools and the unit tests) | 22 or newer; 26.2.0 was used |
| npm | 12.0.2 |
| TypeScript | 7.0.2 |
| esbuild | 0.28.2 |
| oxlint, oxlint-tsgolint, oxfmt | 1.83.0, 7.0.2002, 0.68.0 (oxfmt is pre-1.0, so review its upgrades for formatting changes) |
| `@vscode/vsce`, `ovsx` | 4.0.0, 1.2.0 |
| `@vscode/test-electron` | 3.1.0 |
| `@resvg/resvg-js` (icon rendering only) | 2.6.2 |

## What was tested where

| Platform and editor | Unit tests | Editor tests | Packaged file |
| ------------------- | ---------- | ------------ | ------------- |
| Windows 11, VS Code 1.134 | yes (`npm run test`, also under `bun run`) | yes, against the real command line | yes: installed into a scratch profile and run |
| Linux, Node 22.22 (WSL) | yes, on the built tests | no | no |
| macOS | no | no | no |
| VSCodium | no | no | no |
| Cursor | no | no | no |

Install VSCodium and Cursor, load the packaged file in each, and confirm the three
views, refresh, edit, remove, the command palette entries, and the welcome states
before the first release. The lowest supported editor version is provisional until
then.

## Checking the packaged file

`npm run check:package` builds the package, installs it into a scratch VS Code
profile with the editor's own installer, and runs the editor tests against the
installed copy, so a file missing from the package fails here. It needs `CODE_EXE`
and `MDCOMPOSE_EXE` (see above).

## Placeholders

The publisher id is not chosen yet. It appears as `publisher-tbd` in
`package.json` (the `publisher` field), and the Open VSX namespace is the same
string, because Open VSX asks for the same publisher and namespace as the
Marketplace. When the id is known, replace it everywhere with:

    node scripts/set-publisher.mjs <publisher-id>

The id may use lower-case letters, digits, and hyphens, which satisfies both
registries. The script also covers this file. Nothing else names the publisher, and
a test fails if the placeholder is left in a released package.

Publishing is done by hand, never from a push. The registry accounts and tokens are
set up as described in the `integrations-foundation` change.
