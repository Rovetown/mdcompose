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

The toolchain is Bun first, with npm as a tested fallback. Every script in
`package.json` runs under either, and the source uses no Bun-only API.

    bun ci                 install exactly what bun.lock records
    bun run build          bundle src/extension.ts to dist/extension.js
    bun run typecheck      type-check with tsc
    bun run lint           oxlint, type-aware
    bun run format         oxfmt, check only (format:write fixes)
    bun run test           unit tests, run by Node's test runner
    bun run test:editor    load the extension into a real editor and test it
    bun run package        build the .vsix package

`test:editor` starts a real editor. Set `CODE_EXE` to an installed editor
executable to use it; otherwise the test tool downloads VS Code.

To fall back to npm, delete `bun.lock`, run `npm install`, change the
`packageManager` field in `package.json`, and use `npm run <script>` in place of
`bun run <script>`. Keep exactly one lockfile.

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
