# mdcompose for VS Code, VSCodium, and Cursor

A sidebar for your [mdcompose](https://pypi.org/project/mdcompose/) snippet and
skill libraries. It shows what is in them and the state of the project you have
open, and it runs the matching `mdcompose` commands for you. It is a graphical
layer over the command line, not a replacement: it runs `mdcompose` in the
background and shows the result, and it offers only what the command line offers.

## Requirements

- The `mdcompose` command line, version 0.3.0 or newer. Install it with any of:

      pipx install mdcompose
      uv tool install mdcompose
      pip install mdcompose

  The extension never installs, downloads, or updates it.
- VS Code 1.90 or newer, or a VSCodium or Cursor build of the same generation.

If `mdcompose` is not on your executable search path, set `mdcompose.executablePath`
in your user settings. The sidebar tells you when it cannot find it and offers a
button to set the path.

## What you get

Click the mdcompose icon in the Activity Bar. It holds three views:

- **Snippets** and **Skills** list your libraries: each entry's title, tags, and
  description, and its id when two entries share a title.
  - **Edit** opens the entry's file in an editor tab.
  - **Remove** asks first, then removes it through the command line.
  - **Copy This Project's Snippets (or Skills) Into Library** brings in the ones
    embedded in the current project's manifest (`mdcompose snippet adopt`). If one
    already exists in your library with different content, you choose: keep your
    copies, replace them, or decide one by one in the terminal.
- **Project** shows the state of the folder you have open: whether it is healthy,
  the status of `AGENTS.md` and `CLAUDE.md`, the sync state of each registered
  target, and any warnings.
  - **Recompose Project From Its Saved Selection** re-composes the project from its
    recorded selection. If a managed file was edited by hand, it stops, changes
    nothing, and offers to open the command line's own prompt in a terminal.
  - **Choose Snippets and Skills for This Project** opens `mdcompose init` in a
    terminal, so its picker works unchanged.

Every button is also a command in the command palette, under "mdcompose". In a
window with several folders, project actions ask which folder they apply to.

The views show what was read last time as soon as the editor opens, with the time
it was read, and refresh in the background. If a refresh fails, the old rows stay
with the error beside them.

## Settings

| Setting | Meaning |
| ------- | ------- |
| `mdcompose.executablePath` | Full path to the `mdcompose` executable. Empty means use the search path. |
| `mdcompose.timeoutSeconds` | How long one command may run before it is stopped. Default 30. |

Both can be set only in your user settings. A workspace cannot set them.

## Privacy and safety

- The extension makes no network requests of its own and sends no telemetry.
- The only program it runs is `mdcompose`, with its arguments passed directly and
  no shell in between.
- A workspace cannot choose which program the extension runs: the executable
  setting is accepted only from your user settings.
- In a workspace you have not trusted, the views still read, but the buttons that
  change files are hidden and the commands refuse.
- It keeps a small cache of the last results in the editor's own storage. It never
  writes into your libraries or your project.

## What it does not do

It has no way to create a snippet or a skill, because the command line has none.
Add one by putting a Markdown file in your library folder, or with the command
line's `import` command. Adopted entries come back without their title and tags,
because a project's manifest keeps only the text; add the frontmatter back by
editing the file.

## Supported editors and platforms

One package serves VS Code, VSCodium, and Cursor. It has been tested on Windows
with VS Code 1.134. VSCodium, Cursor, macOS, and Linux have not been tested yet.

## Links

- Source and issues: <https://github.com/Rovetown/mdcompose>
- The command line: <https://pypi.org/project/mdcompose/>
- Licence: MIT
