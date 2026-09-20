# Editor and IDE integrations: evaluation

What an editor integration for mdcompose could do in each candidate editor, what
it costs to build and publish, and what the vendor's terms mean for a developer
working there. This is the evidence behind the first Roadmap item in
[`TODO.md`](../TODO.md) (third-party integrations). Nothing here is built yet.

Research date: 2026-09-20. Vendor terms and plugin systems move quickly; treat
each row as a snapshot and re-check the linked source before building.

Legend: `Y` yes, `N` no, `P` partial, `n/a` does not apply. A trailing `*` or a
`?` means the cell comes from general knowledge or a search snippet, not a
primary document read during this evaluation. Verify every starred cell before
committing effort to that editor (task 3 of the change).

## Candidates

Twelve editors, screened for: free to use, free to develop and publish for, and
no vendor terms that trade away the developer's work to AI training.

| Editor | Kind | Extension host |
| ------ | ---- | -------------- |
| VS Code | mainstream editor | VS Code extension API |
| VSCodium | VS Code build without Microsoft branding and telemetry | same API, Open VSX |
| Cursor | AI-first VS Code fork | same API, Open VSX |
| Windsurf | AI-first VS Code fork (Cognition, folding into Devin Desktop) | same API, Open VSX |
| Kiro | AI-first VS Code fork (AWS) | same API, Open VSX |
| Antigravity | AI-first VS Code fork (Google) | same API, Open VSX |
| JetBrains IDEs | IntelliJ Platform family (IDEA, PyCharm, WebStorm, ...) | IntelliJ Platform SDK |
| Zed | native editor, Rust | WebAssembly extensions |
| Neovim | terminal editor | Lua plugins, RPC hosts |
| Helix | terminal editor | none stable |
| Sublime Text | proprietary editor | Python plugins |
| Visual Studio | Microsoft IDE | VSIX |

Dropped by decision: Xcode, Emacs, Vim.

## 1. Licensing and cost

The screen has three questions. Can a developer use the editor free? Can they
build and publish an extension free? Do the terms let the vendor train on what
the developer does there?

| Editor | Editor cost | Extension dev cost | Publish channel and cost | Data and AI-training terms found | Result |
| ------ | ----------- | ------------------ | ------------------------ | -------------------------------- | ------ |
| VS Code | Free (Microsoft licence, MIT source) | Free | Visual Studio Marketplace, free. Personal access tokens retire 2026-12-01, so publish with Entra ID | Marketplace terms restrict the marketplace to Microsoft products. No clause found that trains on published extensions. Terms not read end to end | PASS |
| VSCodium | Free, MIT binaries, telemetry off | Free, same API | Open VSX, free* (Eclipse publisher agreement*) | None found | PASS |
| Cursor | Free tier and paid | Free (no need to develop inside it) | Open VSX | Privacy Mode is zero retention and no training. On individual plans it is a setting the user must turn on. Terms say no training unless the customer agrees | PASS as a test target |
| Windsurf | Free tier and paid | Free (no need to develop inside it) | Open VSX | Cognition terms allow using customer data for training. Paid tiers can opt out. Product is being merged into Devin Desktop (July 2026) | CAUTION: test target only, and demand may move |
| Kiro | Free (50 credits) and paid | Free (no need to develop inside it) | Open VSX | Free tier and individual plans: content collected for service improvement, including model training, by default. Opt-out is in settings | CAUTION: test target only, opt out first |
| Antigravity | Free tier* | Free (no need to develop inside it) | Open VSX (default registry) | Google states code, prompts, and transcripts are never used to train foundation models. Individual-tier terms not read | PASS with note |
| JetBrains | Free tier of the IDEs; IntelliJ Platform is Apache-2.0 | Free (Gradle plugin, IntelliJ IDEA free tier) | JetBrains Marketplace, free. Needs a developer EULA or an open-source licence, and a privacy policy if personal data is collected | The AI-training prohibition found is in JetBrains' own Free Plugin License, not a term on third-party plugins. Marketplace agreement not read end to end | PASS |
| Zed | Free (GPL, AGPL, Apache) | Free. Rust compiled to `wasm32-wasip2` | Pull request to `zed-industries/extensions`, free. Repo needs an accepted licence (MIT, Apache-2.0, BSD-2, BSD-3, CC BY 4.0, GPLv3, LGPLv3, Unlicense, zlib) | Training only on explicit opt-in | PASS, but see capabilities |
| Neovim | Free (Apache-2.0) | Free | GitHub, no registry | No vendor | PASS |
| Helix | Free (MPL-2.0) | No stable plugin API. A Steel (Scheme) system exists on a fork | none | No vendor | BLOCKED for plugins |
| Sublime Text | Proprietary. Unlimited free evaluation | Free (Python API) | Package Control, free (pull request to its registry)* | None found | PASS, low priority |
| Visual Studio | Community edition free for individuals, open source, and organisations of up to 5 developers | Free | Visual Studio Marketplace, free | Same Marketplace terms as VS Code | PASS, low priority |

### The developer environment is not the test target

The AI-training concern applies to where the developer writes code, not to
where the finished extension is installed. A `.vsix` is built once and can be
developed and tested in VS Code or VSCodium. Cursor, Windsurf, Kiro, and
Antigravity only need the built file installed to check it loads. So a CAUTION
row never forces the developer to work inside an editor whose terms they dislike.

The extension source is public on GitHub either way. What the terms change is
whether private work done inside the editor is used for training, which does not
arise if development stays in VS Code, VSCodium, Neovim, or a JetBrains IDE.

### One package, six editors

VS Code, VSCodium, Cursor, Windsurf, Kiro, and Antigravity share the VS Code
extension API. One `.vsix` built once loads in all six. What differs is the
registry: VS Code reads Microsoft's Marketplace, the other five read Open VSX
(Microsoft's terms forbid forks from using its marketplace). So publishing means
two registry uploads of the same file. The rows stay separate because behaviour
can still differ:

- Microsoft-proprietary extensions and APIs (Copilot APIs, Remote-SSH, Pylance,
  C# Dev Kit, Live Share) are absent in the forks. An extension that avoids them
  behaves the same.
- Each fork lags VS Code by some engine version. The extension manifest declares
  a minimum `engines.vscode`, and the lowest fork sets the floor.
- AI features (rules files, MCP, agent panels) are fork-specific and are not part
  of the shared API.

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
| MCP | MCP server | Contribute or point at a server exposing the library |
| Reads | Reads AGENTS.md | The editor's agent consumes the output mdcompose writes |

| Editor | Cmd | Pick | Stat | Diag | Deco | Panel | Schema | MCP | Reads |
| ------ | --- | ---- | ---- | ---- | ---- | ----- | ------ | --- | ----- |
| VS Code | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| VSCodium | Y | Y | Y | Y | Y | Y | Y | Y* | n/a |
| Cursor | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Windsurf | Y* | Y* | Y* | Y* | Y* | Y* | Y* | Y* | ? |
| Kiro | Y* | Y* | Y* | Y* | Y* | Y* | Y* | Y | Y |
| Antigravity | Y* | Y* | Y* | Y* | Y* | Y* | Y* | Y* | ? |
| JetBrains | Y | Y | Y | Y | Y | Y | Y | ? | ? |
| Zed | P | N | N | N | N | N | P* | Y | Y* |
| Neovim | Y | Y | Y | Y | Y | P | Y* | plugin | plugin |
| Helix | P | N | N | N | N | N | P* | N | n/a |
| Sublime Text | Y | Y | Y | Y | P | P | P* | n/a | n/a |
| Visual Studio | Y* | Y* | Y* | Y* | Y* | Y* | P* | ? | ? |

Notes on the cells that limit a design:

- **Zed extensions have no UI surface.** Verified against its docs: an extension
  can provide languages, debuggers, themes, icon themes, snippets, and MCP
  servers, and nothing else. There is no command, panel, or status API. What Zed
  users can do today is task definitions and settings, so Zed gets documented
  recipes, not an extension.
- **Helix has no stable plugin system.** Keybindings to `:sh` are the ceiling
  until its Steel work merges.
- **Neovim and Sublime need no marketplace.** A small Lua or Python plugin that
  calls the CLI and renders `--json` output covers Cmd through Deco.
- **Reads AGENTS.md.** Cursor and Kiro read `AGENTS.md` natively (Kiro treats it
  as always-included steering). VS Code reads it under a Copilot setting.
  Windsurf documents its own rules file; support for `AGENTS.md` was not
  confirmed. This is the target consumer, not a plugin feature: mdcompose's
  existing output already reaches these editors.
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
| JetBrains | 1 | Wave 2 | Kotlin plugin | High | High | Second codebase, second toolchain |
| Neovim | 1 | Wave 3 | Lua plugin | Medium, loyal | Low | Thin wrapper over the CLI |
| Zed | 1 | Wave 3 | docs, tasks recipes, later maybe MCP | Growing | Low | No extension UI possible |
| Windsurf | 2 | Wave 1 | same `.vsix` | Uncertain | None extra | Ownership in flux |
| Helix | 2 | Wave 3 | docs only | Small | Low | Keybinding recipes only |
| Sublime Text | 3 | Wave 4 | Python plugin | Small | Low | Optional |
| Kiro | 3 | Wave 1 | same `.vsix` | Small | None extra | Test target only, opt out of data sharing |
| Antigravity | 3 | Wave 1 | same `.vsix` | Uncertain | None extra | Test target only |
| Visual Studio | 3 | deferred | VSIX (.NET) | Windows only | High | Poor fit for a cross-platform tool |

The zero-extra-effort rows are the argument for one VS Code extension first: a
single build reaches six of twelve editors once Open VSX publishing is in place.

## 4. Plan

1. **Cross-editor, no plugin:** define JSON Schemas for `mdcompose.lock` and
   snippet frontmatter, and list them in a public schema catalog. Reaches every
   editor with a JSON or YAML language server, including Zed and Helix.
2. **Wave 1, VS Code family:** one TypeScript extension covering Cmd, Pick, Stat,
   Diag, and Deco through the CLI's `--json` output. Publish to both registries.
3. **Wave 2, JetBrains:** a Kotlin plugin with the same capability set, after
   Wave 1 shows which features users actually want.
4. **Wave 3, terminal and Zed:** a Neovim Lua plugin, plus documented recipes for
   Zed tasks and Helix keybindings. No Zed or Helix extension.
5. **Wave 4, optional:** Sublime Text. Visual Studio stays deferred.

Each wave is its own OpenSpec change, started manually. Nothing above changes
`mdcompose/core/`.

## 5. Decisions

Decided (2026-09-20):

- **Where the code lives.** A subdirectory of this repository with one
  sub-subdirectory per editor (for example `integrations/vscode/`), so one
  release train and one CI cover everything. The cost is that the JetBrains
  (Gradle) and Zed (Rust) toolchains sit beside the Python project; each
  integration keeps its own build files inside its own directory.
- **No MCP server.** A `mdcompose mcp` server would let an agent read and act on
  the library. Composing content is a human decision at every trust boundary
  (see the threat model in `AGENTS.md`), so this is rejected, not deferred.
- **No language server.** It would add a large dependency and a long-running
  process for little that the CLI and JSON Schemas do not already cover.

Still open:

- **Plugin licence.** MIT, matching the CLI, satisfies Zed's accepted-licence list
  and JetBrains' open-source path. Proposed, not yet confirmed.

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
- Zed developing extensions: https://zed.dev/docs/extensions/developing-extensions
- Zed publishing guide: https://zed.dev/docs/extensions/publishing/publishing-guide
- Zed terms and AI training: https://zed.dev/docs/ai/ai-improvement
- Cursor data use: https://cursor.com/data-use
- Windsurf and Cognition terms: https://windsurf.com/terms-of-service-individual
- Kiro data protection: https://kiro.dev/docs/privacy-and-security/data-protection/
- Kiro steering and AGENTS.md: https://kiro.dev/docs/steering/
- Antigravity extensions: https://antigravity.google/docs/ide/extensions/
- Helix plugin system discussion: https://github.com/helix-editor/helix/discussions/3806
- Sublime Text: https://en.wikipedia.org/wiki/Sublime_Text
- Visual Studio Community licence: https://visualstudio.microsoft.com/vs/community/
- Neovim remote plugins: https://neovim.io/doc/user/remote_plugin/
