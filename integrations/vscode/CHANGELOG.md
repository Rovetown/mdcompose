# Changelog

All notable changes to this extension. It is versioned on its own, separately from
the mdcompose command line.

## Unreleased

First version, not yet published.

- A sidebar with three views: Snippets, Skills, and Project.
- Edit, remove, and adopt for snippets and skills; reapply and change selection for
  the project. Every action is also in the command palette.
- Results are cached in the editor's storage and shown at once on start, then
  refreshed in the background.
- Works with mdcompose 0.3.0 or newer.
- No network requests and no telemetry. In a workspace that is not trusted the views
  read and the buttons that change files are hidden.
