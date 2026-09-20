# Editor and IDE integrations: evaluation

What an editor integration for mdcompose could do in each candidate editor, what
it costs to build and publish, and what the vendor's terms mean for a developer
working there. This is the evidence behind the first Roadmap item in
[`TODO.md`](../TODO.md) (third-party integrations). Nothing here is built yet.

Research date: 2026-09-20. Vendor terms and plugin systems move quickly; treat
each row as a snapshot and re-check the linked source before building.

Legend: `Y` yes, `N` no, `P` partial, `n/a` does not apply. A trailing `*` means
the cell is inferred (for example "it is a VS Code fork, so it should support
this") or came from a search snippet, not from a primary document read during
this evaluation. A `?` means unknown. Verify every starred or unknown cell
before committing effort to that editor (task 3 of the change). Cells without a
mark were checked against a primary source.

## Candidates

Seven editors, screened for: free to use, free to develop and publish for, and
no vendor terms that trade away the developer's work to AI training.

| Editor | Kind | Extension host |
| ------ | ---- | -------------- |
| VS Code | mainstream editor | VS Code extension API |
| VSCodium | VS Code build without Microsoft branding and telemetry | same API, Open VSX |
| Cursor | AI-first VS Code fork | same API, Open VSX |
| Antigravity | AI-first VS Code fork (Google) | same API, Open VSX |
| JetBrains IDEs | IntelliJ Platform family (IDEA, PyCharm, WebStorm, ...) | IntelliJ Platform SDK |
| Neovim | terminal editor | Lua plugins, RPC hosts |
| Visual Studio | Microsoft IDE | VSIX |

### Removed from the evaluation

Dropped by decision, and not planned for now. Users of these editors run the CLI
(and later the TUI) from a terminal, the same as with any editor not listed.

| Editor | Reason |
| ------ | ------ |
| Zed | Extensions have no UI surface (languages, themes, debuggers, snippets, and MCP servers only), so no integration of the kind needed is possible yet |
| Helix | No stable plugin system |
| Sublime Text | Small reach for the effort |
| Windsurf | Near-duplicate of Cursor for extension purposes; free-tier terms allow training by default; ownership in flux (folding into Devin Desktop) |
| Kiro | Small reach; free-tier terms allow training by default |
| Xcode, Emacs, Vim | Dropped earlier |

Revisit any of them if its extension surface changes or demand appears.

## 1. Licensing and cost

The screen has three questions. Can a developer use the editor free? Can they
build and publish an extension free? Do the terms let the vendor train on what
the developer does there?

| Editor | Editor cost | Extension dev cost | Publish channel and cost | Data and AI-training terms found | Result |
| ------ | ----------- | ------------------ | ------------------------ | -------------------------------- | ------ |
| VS Code | Free (Microsoft licence, MIT source) | Free | Visual Studio Marketplace, free. Personal access tokens retire 2026-12-01, so publish with Entra ID | Marketplace terms restrict the marketplace to Microsoft products. No clause found that trains on published extensions. Terms not read end to end | PASS |
| VSCodium | Free, MIT binaries, telemetry off | Free, same API | Open VSX, free. Needs an Eclipse account, a signed Eclipse publisher agreement, then an access token and a namespace via `ovsx` | None found | PASS |
| Cursor | Free tier and paid | Free (no need to develop inside it) | Open VSX (Cursor has no marketplace of its own) | Cursor's terms cover the code and prompts a Cursor user sends to its AI, not extension uploads. Privacy Mode is zero retention and no training; on individual plans the user must turn it on | PASS as a test target |
| Antigravity | Free tier (sign in with a Google account) | Free (no need to develop inside it) | Open VSX (default registry)* | Individual accounts fall under Google's terms and privacy policy plus Antigravity's additional terms: Google records and stores usage and interaction data (deletable on request) and uses it under that agreement. The "never trains on your code" statement applies to enterprise (Google Cloud) accounts only | CAUTION: test target only |
| JetBrains | Free tier of the IDEs; IntelliJ Platform is Apache-2.0 | Free (Gradle plugin, IntelliJ IDEA free tier) | JetBrains Marketplace, free. Needs a developer EULA or an open-source licence, and a privacy policy if personal data is collected | The AI-training prohibition found is in JetBrains' own Free Plugin License, not a term on third-party plugins. Marketplace agreement not read end to end | PASS |
| Neovim | Free (Apache-2.0) | Free | GitHub, no registry | No vendor | PASS |
| Visual Studio | Community edition free for individuals, open source, and organisations of up to 5 developers | Free | Visual Studio Marketplace, free | Same Marketplace terms as VS Code | PASS, low priority |

### What the Cursor training terms cover

Cursor's training terms are about the person using Cursor, not about extension
authors. Specifically:

- **Uploading a plugin.** Not to Cursor. Cursor reads the Open VSX registry, and
  you publish there. Cursor's terms do not govern that upload, and none of the
  terms read mention extensions at all.
- **Someone using your plugin in Cursor.** Cursor's terms cover the code and
  prompts that user sends through Cursor's AI features. With Privacy Mode off,
  Cursor may keep and use that content unless the plan or terms say otherwise;
  with it on, there is zero retention and no training. That is the user's
  content and their setting, not your plugin's code. mdcompose runs locally and
  sends nothing, so the plugin adds no data flow to Cursor's servers.
- **Your plugin's source.** It is public open source on GitHub either way, so
  anyone, including a vendor, can already read it.

So the real concern is narrower than it sounds: it is where a developer writes
private code, not where a finished extension is installed. Development stays in
VS Code, VSCodium, Neovim, or a JetBrains IDE, and Cursor and Antigravity only
need the built file installed to check that it loads. Antigravity is the same
class as the removed Kiro and Windsurf: individual accounts have their data
collected. It stays only as an install-and-check target, and can be dropped
like them.

### One package, four editors

VS Code, VSCodium, Cursor, and Antigravity share the VS Code extension API. One
`.vsix` built once loads in all four. What differs is the registry: VS Code
reads Microsoft's Marketplace, the other three read Open VSX (Microsoft's terms
forbid forks from using its marketplace). So publishing means two registry
uploads of the same file. The rows stay separate because behaviour can still
differ:

- Microsoft-proprietary extensions and APIs (Copilot APIs, Remote-SSH, Pylance,
  C# Dev Kit, Live Share) are absent in the forks. An extension that avoids them
  behaves the same.
- Each fork lags VS Code by some engine version. The extension manifest declares
  a minimum `engines.vscode`, and the lowest fork sets the floor.
- AI features (rules files, agent panels) are fork-specific and are not part of
  the shared API.

## 2. What an integration can do

mdcompose already gives every wrapper what it needs: `--json` on every report
command, stable exit codes, and a flag for every prompt. A wrapper never needs
to reimplement core behavior; it shells out and renders the result.

Capabilities, ordered from cheapest to most work:

| Code | Capability | What it does |
| ---- | ---------- | ------------ |
| Cmd | Run commands | Expose `init`, `doctor`, `snippet list`, `skill list` as editor commands |
| Pick | Pickers | Native selection UI for snippets and skills, passed to the CLI as flags |
| Stat | Status | A drift and health indicator from `doctor --json` |
| Diag | Diagnostics | Drift and lock problems shown as editor problem markers |
| Deco | Block decoration | Highlight, fold, or mark managed-block regions |
| Panel | Custom panel | A tree or webview for browsing the library |
| Schema | JSON Schema | Validate `mdcompose.lock` and snippet frontmatter |
| Reads | Reads AGENTS.md | The editor's agent consumes the output mdcompose writes |

An MCP server capability is deliberately not a column: it is rejected (see
Decisions).

| Editor | Cmd | Pick | Stat | Diag | Deco | Panel | Schema | Reads |
| ------ | --- | ---- | ---- | ---- | ---- | ----- | ------ | ----- |
| VS Code | Y | Y | Y | Y | Y | Y | Y | Y |
| VSCodium | Y | Y | Y | Y | Y | Y | Y | n/a |
| Cursor | Y | Y | Y | Y | Y | Y | Y | Y |
| Antigravity | Y* | Y* | Y* | Y* | Y* | Y* | Y* | N (not documented) |
| JetBrains | Y | Y | Y | Y | Y | Y | Y | ? |
| Neovim | Y | Y | Y | Y | Y | P | Y* | plugin |
| Visual Studio | Y* | Y* | Y* | Y* | Y* | Y* | P* | ? |

Notes on the cells that limit a design:

- **Neovim needs no marketplace.** A small Lua plugin that calls the CLI and
  renders `--json` output covers Cmd through Deco.
- **Reads AGENTS.md.** Cursor reads `AGENTS.md` natively. VS Code reads it under
  a Copilot setting. Antigravity documents its own rule locations (`.agents/rules/` and `~/.gemini/GEMINI.md`) and does not mention `AGENTS.md`. This is the target consumer, not
  a plugin feature: mdcompose's existing output already reaches these editors.
- **Every JSON-shaped capability (Schema) has a cheap route:** publish JSON
  Schemas for `mdcompose.lock` and snippet frontmatter once to a public schema
  catalog. Editors with a JSON or YAML language server then validate without any
  mdcompose-specific plugin. The schemas do not exist yet.

## 3. Effort, reach, and order

| Editor | Tier | Suggested wave | Build | Reach | Effort | Notes |
| ------ | ---- | -------------- | ----- | ----- | ------ | ----- |
| VS Code | 1 | Wave 1 | one `.vsix` (TypeScript) | Very high | Medium | Publish to Marketplace and Open VSX |
| VSCodium | 1 | Wave 1 | same `.vsix` | Low, but free | None extra | Open VSX listing covers it |
| Cursor | 1 | Wave 1 | same `.vsix` | High | None extra | Test target only |
| Antigravity | 3 | Wave 1 | same `.vsix` | Uncertain | None extra | Test target only |
| JetBrains | 1 | Wave 2 | Kotlin plugin | High | High | Second codebase, second toolchain |
| Neovim | 1 | Wave 3 | Lua plugin | Medium, loyal | Low | Thin wrapper over the CLI |
| Visual Studio | 3 | deferred | VSIX (.NET) | Windows only | High | Poor fit for a cross-platform tool |

The zero-extra-effort rows are the argument for one VS Code extension first: a
single build reaches four of seven editors once Open VSX publishing is in place.

## 4. Plan

1. **Cross-editor, no plugin:** define JSON Schemas for `mdcompose.lock` and
   snippet frontmatter, and list them in a public schema catalog. Reaches every
   editor with a JSON or YAML language server.
2. **Wave 1, VS Code family:** one TypeScript extension covering Cmd, Pick, Stat,
   Diag, and Deco through the CLI's `--json` output. Publish to both registries.
3. **Wave 2, JetBrains:** a Kotlin plugin with the same capability set, after
   Wave 1 shows which features users actually want.
4. **Wave 3, Neovim:** a Lua plugin.
5. **Deferred:** Visual Studio, and every editor in "Removed from the evaluation".

Each wave is its own OpenSpec change, started manually. Nothing above changes
`mdcompose/core/`.

## 5. Decisions

Decided (2026-09-20):

- **Where the code lives.** A subdirectory of this repository with one
  sub-subdirectory per editor (for example `integrations/vscode/`), so one
  release train and one CI cover everything. The cost is that the JetBrains
  (Gradle) toolchain sits beside the Python project; each integration keeps its
  own build files inside its own directory.
- **No MCP server.** A `mdcompose mcp` server would let an agent read and act on
  the library. Composing content is a human decision at every trust boundary
  (see the threat model in `AGENTS.md`), so this is rejected, not deferred.
- **No language server.** It would add a large dependency and a long-running
  process for little that the CLI and JSON Schemas do not already cover.
- **Editor scope.** Kiro, Windsurf, Zed, Helix, and Sublime Text are removed for
  now; their users run the CLI or TUI from a terminal.

Still open:

- **Plugin licence.** MIT, matching the CLI, satisfies JetBrains' open-source
  path. Proposed, not yet confirmed.

Rules that hold for every integration:

- **Invariants.** An extension makes no network requests and sends no telemetry,
  matching the CLI, and it drives the CLI only through flags, never by scripting
  an interactive prompt.

## Sources

- Open VSX registry and its users: https://thehackernews.com/2026/01/vs-code-forks-recommend-missing.html
  and https://en.wikipedia.org/wiki/Open_VSX
- Visual Studio Code publishing: https://code.visualstudio.com/api/working-with-extensions/publishing-extension
- Microsoft Publisher Agreement: https://learn.microsoft.com/en-us/legal/marketplace/msft-publisher-agreement
- JetBrains Free Plugin License: https://www.jetbrains.com/legal/docs/terms/jetbrains-free-plugin-license/1.1/
- JetBrains Marketplace approval guidelines: https://plugins.jetbrains.com/docs/marketplace/jetbrains-marketplace-approval-guidelines.html
- IntelliJ Platform SDK: https://plugins.jetbrains.com/docs/intellij/welcome.html
- Cursor data use: https://cursor.com/data-use
- Antigravity terms, rules, and extensions: https://antigravity.google/terms,
  https://antigravity.google/docs/rules-workflows, https://antigravity.google/docs/ide/extensions/
- Open VSX publishing: https://github.com/EclipseFdn/open-vsx.org/wiki/Publishing-Extensions
- Neovim remote plugins: https://neovim.io/doc/user/remote_plugin/
- Visual Studio Community licence: https://visualstudio.microsoft.com/vs/community/
- Removed editors, for reference: https://zed.dev/docs/extensions/developing-extensions,
  https://github.com/helix-editor/helix/discussions/3806,
  https://windsurf.com/terms-of-service-individual,
  https://kiro.dev/docs/privacy-and-security/data-protection/
