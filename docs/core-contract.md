# mdcompose core behavior contract

This document specifies the behavior of mdcompose's core layer without reference
to any programming language. The Python package in `mdcompose/core/` is one
implementation of it. A port to another language reimplements this contract
rather than translating that code, so this document is the authority on what
correct behavior is.

It is written alongside the code rather than after it. When behavior changes,
this document changes in the same commit.

Scope so far covers the foundations, `doctor`, the managed block, the manifest,
drift detection, the snippet library, and composition. Sections are added as
later changes land. Anything not described here is not yet specified.

Terms used throughout:

- **generated text** is any string mdcompose composes itself: a message, a
  prompt, a label, a report line, a JSON document.
- **transported content** is text that originated elsewhere and passes through
  mdcompose unchanged: a snippet body, a section extracted from a file.

---

## 1. Exit codes

Every command exits with exactly one of three codes.

| Code | Meaning |
| ---- | ------- |
| 0 | Success, and nothing needs attention. |
| 1 | mdcompose worked correctly and is reporting a real condition the user or the environment must resolve. |
| 2 | mdcompose could not do its job. A usage error, or an unexpected internal failure. |

Codes 1 and 2 are distinguished by fault. A continuous integration job treats
both as failure; a person reading the code learns whether to look at their own
project or to file a bug.

Declining an optional action a command offered is success, not failure. The user
was asked, and answered.

There is exactly one error boundary per invocation. The core layer signals a
code 1 condition by raising a distinguished error type carrying a human-readable
message; that message names the thing at fault, usually a path. The boundary
catches it, writes the message to the error stream, and returns code 1. Any
other unexpected failure is caught by the same boundary and becomes code 2 with
a message saying it is a bug in mdcompose. The core layer never catches its own
condition type to decide what to do next: the type is an error boundary
mechanism, not a control flow mechanism.

## 2. Output discipline

Requested output goes to the standard output stream. Errors, warnings, and
interactive prompts go to the standard error stream. Redirecting standard output
to a file therefore never hides a warning, and an interactive run remains
pipeable.

Four kinds of write exist:

| Kind | Stream | Suppressed by quiet mode | ASCII enforced |
| ---- | ------ | ------------------------ | -------------- |
| informational | standard output | yes | yes |
| explicitly requested | standard output | no | yes |
| warning | standard error | no | yes |
| error | standard error | no | yes |
| transported content | standard output | no | no |

A report is informational: quiet mode reduces a command to its exit code, which
is what a continuous integration gate wants. A machine-readable document is
explicitly requested output, because the caller asked for it by name.

### 2.1 Machine-readable output

Every command that produces a report supports a machine-readable mode. In that
mode the standard output stream carries one valid JSON document and nothing
else, so it can be piped directly to a consumer. Warnings still go to the error
stream, which is what makes that guarantee possible.

Every object in the document has a stable set of keys. A field that has no value
is present and null rather than omitted, so a consumer never has to branch on
which keys exist.

A machine-readable run never prompts. When it needs an answer that no argument
supplied, it reports which answer is missing and which argument supplies it, and
exits 1. It does not silently accept a default, because output that looks
authoritative but answers a different question is worse than a refusal.

### 2.2 Colour

Output is colourized only when the standard output stream is a terminal. Colour
is disabled when the `NO_COLOR` environment variable is present, when the user
passes the no-colour argument, and in machine-readable mode.

Colour never carries meaning on its own. Whatever a decoration conveys, the
plain text conveys the same thing, so a colourless terminal loses nothing.

### 2.3 Generated text is plain ASCII

Every character mdcompose generates itself is ASCII. No emoji, no em dash, no en
dash, no arrow, no smart quote, anywhere in a message, a prompt, a label, a
report, or a file mdcompose authors.

This is an encoding requirement, not a style preference. A Windows console
running a cp1252 or cp437 code page cannot encode those characters at all, so
emitting one raises an encoding error on a platform this project treats as
primary. Emoji additionally have ambiguous terminal width, which breaks the
column alignment in a report, and screen readers announce them verbatim.

Transported content is exempt and is never altered. A snippet body containing
emoji composes into a file unchanged. An implementation should enforce the rule
at the point where generated text is written, so a latent violation surfaces as
a clear internal failure naming the offending characters rather than as an
encoding error deep in the runtime.

### 2.4 Scriptability

Every prompt in every command has a corresponding argument that supplies the
same answer directly. This holds for destructive prompts too. A command must be
fully runnable unattended, not merely runnable with every default accepted.

Supporting only "accept all defaults" would make automation possible for exactly
one set of choices, which is not automation.

## 3. Platform detection

Detection runs once per invocation and produces an immutable result that is
passed to everything that needs it. No two parts of one command can therefore
disagree about the platform.

The result has two independent fields.

**Operating system** is exactly one of `windows`, `macos`, or `linux`. A
platform matching none of the three is reported as unsupported and exits 1.

**WSL status** is a boolean, never a fourth operating system value. WSL is Linux
for every filesystem and path purpose and differs in only two places: the
warning about Windows drives mounted under `/mnt/`, and the fact that a
Windows-side installation resolves a different snippet library. Modelling it as
a separate operating system would force every piece of code that cares about
POSIX semantics to special-case it.

WSL status is true when the operating system is `linux` and at least one
indicator is present:

- a Microsoft or WSL marker in the kernel version string, and
- any WSL-specific environment variable.

Any single indicator is sufficient. Microsoft has changed both the kernel string
and the environment variables between WSL 1 and WSL 2, so relying on one signal
would fail on some installations. A false negative degrades to plain Linux,
which resolves correct paths and merely omits two warnings.

Indicators are never consulted when the operating system is not `linux`. A stray
environment variable on Windows or macOS cannot produce a WSL result.

## 4. Path resolution

Resolution reports what a path would be and what is currently true about it. It
never creates a file or a directory.

Resolving a path expands a leading home-directory marker and anchors a relative
path to the current working directory. The result carries three facts:

- the absolute path,
- whether it currently exists,
- whether it lies on a Windows drive mounted under `/mnt/`.

A path that does not exist is reported as absent rather than raising, and so is
one that cannot be inspected at all, for instance because the user lacks
permission to stat it. A tool whose job is reporting on paths must not fail
because one path is unreadable, and withholding the whole report would hide the
entry that explains the problem. An implementation should decide this itself
rather than relying on its standard library, whose behavior here varies across
versions.

A value that cannot be turned into a path at all is different: that is a
condition the user must fix, and it is reported as one.

The mount flag is per path, not per process: under WSL a user can run from inside the Linux
filesystem while a configured path points at a Windows drive, or the reverse, so
a single process-level flag would misreport both cases. It is always false when
WSL status is false.

### 4.1 The global config directory

One directory per platform holds the global config: an XDG-style user config
path on Linux and macOS, the user application data directory on native Windows.

WSL gets no special case. The platform's own convention already resolves to an
XDG path inside the WSL filesystem, which is the desired answer. Resolving the
directory does not create it.

An environment variable overrides the location when set to a non-empty value.
Without one there is no way to point mdcompose at a different config and library,
which makes the library commands impossible to exercise end to end without
writing into the user's real library. On Windows the platform location comes from
the known-folder API rather than an environment variable, so redirecting the
usual application-data variable does not work and this override is the only
mechanism.

### 4.2 Managed file locations

At global scope, the global CLAUDE.md is at `~/.claude/CLAUDE.md`, a location
fixed by Claude Code rather than chosen by mdcompose. The global AGENTS.md is
wherever the config says, and may be unconfigured.

At project scope, a target directory holds `CLAUDE.md`, `AGENTS.md`, and
`mdcompose.lock`. Each target directory is independent and holds its own
manifest. A parent directory's manifest is never consulted when resolving a
subdirectory.

## 5. Files: encoding, byte order marks, line endings

### 5.1 Reading

Text is read as UTF-8. A leading byte order mark is accepted and removed before
anything else happens, so it never appears in extracted content and never
affects a hash.

Input that is not valid UTF-8 is refused, naming the path. Invalid bytes are
never replaced with substitution characters: decoding a mis-encoded file into
replacement characters would silently corrupt the user's content and then hash
the corruption, which is worse than refusing to read it.

A missing file, a path that is not a file, and a file that cannot be read for
permission reasons are all refused, naming the path.

A file past a fixed size limit is refused rather than read into memory. Every
file mdcompose handles is a markdown config document, kilobytes at most; a file
orders of magnitude larger is a mistake or a hostile input, and refusing it by
name is better than an out-of-memory failure. The limit is generous enough that
no real config file approaches it.

Line endings are returned exactly as stored, so a caller can write the file back
in its original convention.

### 5.2 Normalization and comparison

A canonical form exists for comparison and hashing: the byte order mark removed,
and every line ending converted to a single line feed.

Two pieces of content are equal when their canonical forms are equal. Content
differing only by a byte order mark, or only by line ending convention, is the
same content. A difference in trailing blank lines is a real difference and
survives normalization.

A hash is computed over the canonical form. The same content therefore produces
the same hash on Windows, under WSL, and on Linux, which is what allows a hash
to be recorded in a committed file. Without this, a checkout using one line
ending convention would report a difference from a checkout using the other, on
a file nobody had touched.

### 5.3 Writing

Files are written as UTF-8 with no byte order mark, including when the file being
replaced had one.

An existing file keeps its own dominant line ending convention. A newly created
file uses line feeds. A file mixing both conventions has no correct answer, so
the more frequent wins and an exact tie resolves to line feeds.

Preserving the existing convention matters because rewriting a file that used
carriage return and line feed pairs as line feeds alone would make a version
control system report every line as changed. It is only safe because comparison
normalizes, so preserving the original convention cannot itself cause a spurious
difference. These two rules hold each other up: neither is correct alone.

A write that would produce content equal to what the file already holds, under
normalization, is detected and reported as no change needed.

Every write is atomic. The bytes go to a scratch file in the same directory and
are renamed over the target, so an interrupted write leaves the previous file
whole rather than a truncated one, no reader ever sees a half-written file, and
no scratch artifact remains after a failure. When the target is a symlink the
link is replaced by a real file rather than written through, so a write cannot
land outside the directory it names. This is not only the config: the same
guarantee covers every managed file, the manifest, and every snippet.

## 6. The global config

The global config is a single JSON document in the global config directory. It
holds user preferences only. Per-project state belongs in that project's
manifest.

An absent config file is a valid state, not an error, and yields an instance
where every field is unset. Reading never creates the file or its directory.

Recognized fields:

| Field | Type | Notes |
| ----- | ---- | ----- |
| schema version | whole number | describes the file format |
| snippet library path | string | unset means the default location |
| default mode | `import` or `copy` | the suggestion when setting up a project |
| global CLAUDE.md record | object with a path and a mode | |
| global AGENTS.md path | string | may be unset |

Two validation policies apply, and they are deliberately opposite:

- An **unrecognized** field is preserved on read. A config written by a newer
  version of mdcompose must not be stripped by an older one.
- A **recognized** field holding a value of the wrong type is refused, naming the
  file and the offending field. Silently coercing it would produce a wrong path
  rather than an error.

A malformed document, a top level that is not an object, and a mode outside the
allowed values are all refused, naming the file and the specific problem.

### 6.0 Showing the config

`config show` prints every recognized field with its effective value, marking
each as explicitly set, taken from a default, or not configured, and marking a
field mdcompose does not recognize as unrecognized. It also prints the resolved
path of the config file. With no config file it prints every field's default or
not-configured state, creates nothing, and exits 0.

### 6.0a Writing the config

Reading the config creates nothing. A write creates the file and the config
directory holding it when they do not exist, and a newly created file records the
schema version this mdcompose writes.

A value is validated before the file is touched, so a rejected value cannot have
changed it. A path field is stored expanded to an absolute path, so the recorded
value is exactly what will be used rather than a string that means different
things under different home directories; a leading-slash POSIX path is kept as
written even where the running platform would not call it absolute. A key is
addressed by a dotted path when it names a field inside a nested object, so the
mode inside the global CLAUDE.md record is `claude_global.mode`. The schema
version is not a settable key: it describes the format, not a preference. A key
naming no recognized field is refused rather than written as a field nothing
reads, while an unrecognized field already in the file is still carried through
every write.

Every write is atomic (5.3), which matters most here: a truncated config would
lose the snippet library path, a worse failure than any this tool could report.
A shorter config replaces a longer one with no residue.

Unsetting a key removes it so the field falls back to its default or to not
configured. Unsetting a key that is already absent changes nothing and is not an
error.

Editing opens the config, or the current defaults when no file exists, in the
configured editor. The result is validated as a candidate by the same rules a
file gets; an edit that is not valid JSON or that violates the schema is refused
and the existing config is left byte-identical. A save that changed nothing
writes nothing. With no editor configured, editing is refused.

### 6.1 The snippet library location

The library is the directory named by the snippet library path field. When that
field is unset, it defaults to a `snippets` directory inside the global config
directory.

Resolving the library never creates the directory. An absent library is an empty
library, not an error.

Because the config directory differs per platform, the same user running on
native Windows and under WSL resolves two different libraries. Both answers are
correct for their environment. Setting the field explicitly in both environments
is how a user shares one library, and doing so also suppresses the warning
described below.

### 6.2 The global AGENTS.md path

This field names one canonical global AGENTS.md. It may be unset, and unset is a
healthy state: a user who only manages project-scoped files never needs one.

The field names a single file, not a set of locations. Setting it never causes
content to be written to any other tool-specific location. Projecting the
canonical content to additional locations is a separate operation that requires
each location to be registered explicitly.

The path is chosen lazily. Only a command that writes to the global file pair
prompts for it; a read-only command reports it as not configured and continues.
The prompt offers a default, a second well-known location, and a free-text
custom path, and has an argument equivalent like every other prompt.

## 7. The doctor command

`doctor` reports what mdcompose detected and resolved, so a user or a continuous
integration job can confirm the tool is looking at the right paths before
anything writes.

It reports the operating system, the WSL status, and every resolved path with
its status. A path is `present`, `absent`, or `not configured`. Paths covered:
the config directory, the config file, the snippet library, the global CLAUDE.md,
the global AGENTS.md, the target directory, and that directory's CLAUDE.md,
AGENTS.md, and manifest.

### 7.1 No side effects

`doctor` creates nothing, modifies nothing, deletes nothing, and never prompts.
It is safe to run in any directory and in any automated context. Running it with
no config present reports the config as absent and leaves the filesystem
untouched.

### 7.2 Warnings

Warnings are derived from what was resolved rather than from the process.

A path on a Windows drive mounted under `/mnt/` while WSL status is true produces
one warning naming that path, because crossing the WSL and Windows filesystem
boundary has its own performance and permission characteristics. Each path warns
separately, so a project on a mounted drive can warn while a config directory
inside the Linux filesystem does not.

When WSL status is true and the snippet library path is not explicitly set,
`doctor` warns that a Windows-side installation resolves a different library and
names the field that unifies them. The warning stops once the field is set: a
user who has already chosen does not need telling.

On Windows, a resolved path at or under a OneDrive sync root produces one
warning per path, naming the path, the root, and a link. OneDrive is detected
from the `OneDrive`, `OneDriveConsumer`, and `OneDriveCommercial` environment
variables, then from each account's recorded sync folder, then from a path
component named `OneDrive` or `OneDrive - <org>`. The warning names the concrete
failures: a Files On-Demand placeholder an AI agent reads as empty, a sync race
against a `mdcompose.lock` write and the conflict copy it leaves, and the
260-character path limit. It is a Windows-only signal and, like every warning,
never changes the exit code. The same warning is emitted by `init` before it
writes into such a folder.

A warning alone does not change the exit code. It reports a condition worth
knowing rather than one that must be resolved.

### 7.3 Exit code

`doctor` exits 0 when everything it checks is healthy, including when the global
AGENTS.md is not configured and when a warning was emitted. It exits 1 when a
condition needs attention: an unclassifiable platform, or a config file that
exists but cannot be used.

That makes it usable as a gate without parsing its output, and its
machine-readable mode carries every field of the human-readable report for
callers that want the detail.

## 8. The managed block

A managed block is the region of a file mdcompose owns exclusively. Everything
outside it belongs to the user and is never added to, removed, reordered, or
reformatted by any operation. That single rule is what makes it safe to
regenerate a file the user also edits by hand.

### 8.1 Marker format

A block is delimited by two HTML comment markers carrying the same block id:

    <!-- mdcompose:<block-id>:start -->
    <!-- mdcompose:<block-id>:end -->

A block id is lowercase letters and digits in hyphen-separated groups. The
markers are HTML comments so they render as nothing in any markdown viewer.

This format is a compatibility surface. Once a user has managed blocks in their
files, changing the markers orphans every block already written, and the tool
would silently treat a previously-managed region as user text. It cannot be
changed without a migration command that rewrites existing files.

A marker is recognized only when it is alone on its line. Leading and trailing
whitespace is allowed, so an indented marker still works, but a marker sharing
its line with other text is not a marker. This makes the parser a line scanner
rather than a substring search.

A line inside a fenced code block is never a marker, however exactly it matches.
A marker quoted as an example is documentation. Without this rule, anyone who
writes about the format in their own AGENTS.md would have their file reported as
malformed. A fence closes only on a fence of the same character, at least as long
as the one that opened it, carrying no info string.

### 8.2 Content boundaries

Block content is the lines strictly between the markers. The marker lines are not
content. A start marker immediately followed by its end marker is a valid block
whose content is empty.

### 8.3 Malformed markers

An implementation refuses to guess at boundaries it cannot determine. These
arrangements are malformed:

- a start marker with no matching end marker,
- an end marker with no matching start marker before it,
- two blocks sharing one block id in the same file,
- a block whose markers enclose a block with a different id.

Each is reported naming the file, the block id or ids, and the line numbers
involved, so the user can go straight to the place that needs fixing. Two
complete blocks with different ids in one file are not an error.

Two entry points exist. One reports a malformed file as data and never fails, so
a command reporting on several files can list one bad file beside several good
ones. The other refuses, which is what a write path needs, because writing into a
file whose boundaries are unknown risks destroying user content.

### 8.4 Hashing

A block hash covers block content only. Never the whole file, never the marker
lines. Content is normalized before hashing per section 5.2, so the hash is
unaffected by line ending convention or a byte order mark.

Two consequences follow, and both are load-bearing. An edit anywhere outside the
block cannot change the hash, so a user editing their own prose can never produce
a false drift report. And two machines on different platforms composing the same
content compute the same hash, which is what allows a manifest holding hashes to
be committed.

## 9. The project manifest

The manifest is a JSON file named `mdcompose.lock` in a target directory. Its
presence means mdcompose has composed that directory; its absence means it has
not, which is a state rather than a fault.

It is intended for version control. The filename does not begin with a dot,
because the file is committed and read by people reviewing changes.

### 9.1 No machine-specific state

The manifest contains no absolute paths, no operating system, no WSL status, and
no hostname. The same file is correct for every machine that checks out the
project. Recorded paths are relative to the target directory, and an absolute
path is refused on read.

An implementation does not add the manifest to any ignore file, and does not treat
its presence in version control as a problem.

### 9.2 Schema

| Field | Meaning |
| ----- | ------- |
| schema version | the format this file was written in |
| generated by | the version string of the mdcompose that wrote it |
| generated at | when it was written |
| detected stack | the signal files found when it was composed |
| snippets | the composed snippets, in order, with content embedded |
| files | one entry per managed file, keyed by which file it is |

Each file entry carries a project-relative path, a mode of `import` or `copy`,
and the recorded hash of that file's managed block. An import-mode entry also
records what it imports.

Unrecognized fields are preserved on read. A schema version higher than the
implementation understands is refused, naming the file and both versions, rather
than read with the wrong field meanings. That policy is deliberately stricter than
the config's, because the manifest holds state that write decisions depend on, and
because a committed manifest makes version skew between two contributors more
likely, not less.

The document is formatted for a person to read, since it appears in diffs.

### 9.3 Embedded snippet content

Each snippet entry carries its id, its position in the composition, what it
applies to, and its full markdown content.

Content is embedded rather than referenced because snippet ids resolve against a
personal library that nobody else has. A manifest carrying only ids would be
useless to anyone but its author. Embedding makes it self-contained: a stranger
clones the project and reproduces the same files with an empty library. An entry
without content is refused, naming the snippet.

Composition order comes from the manifest alone, so a reader never needs a library
to know what goes where.

## 10. Drift detection

Drift is the difference between what the manifest recorded and what the managed
files currently hold. It has exactly one implementation, used by every command
that reports drift and by every command that acts on it, so a reporting command
and a writing command can never disagree about the state of a file.

Five states exist, not two:

| State | Meaning |
| ----- | ------- |
| clean | the block's current hash equals the recorded hash |
| drifted | the block exists and its hash differs |
| missing | the manifest records a file that is no longer on disk |
| block-removed | the file exists but its recorded block is gone |
| malformed | the markers cannot be parsed, so no hash can be computed |

Collapsing these into a single drifted state would send a recovery path in the
wrong direction. Restoring a deleted file is not the same operation as
reconciling an edited block, and neither is repairing markers a user broke by
hand.

Because the hash covers only the block, an edit outside the block is clean. And
because content is normalized before hashing, a fresh clone is clean regardless of
the line ending convention the checkout used.

Detection reads only. Neither the managed files nor the manifest is modified by
determining their state.

## 11. Doctor and drift

`doctor` reports a state for every managed file the manifest records, and reports
the target as not initialized when there is no manifest. Not initialized is not a
fault and exits 0.

Any state other than clean is a condition the user must resolve, so it exits 1.

`doctor` reports and never repairs. It does not rewrite a drifted block, restore a
missing file, reinsert a removed block, or update the manifest to match what it
found. It does not prompt, even when it finds drift.

A malformed file is reported as that file's state rather than aborting the run, so
one unparseable file never costs the user the report that explains the rest of
their project.

## 12. The snippet library

The library is a flat directory of markdown files, one snippet per file. A
snippet is YAML frontmatter followed by markdown body content, and its id is its
filename with the extension removed. There is no id field: two sources of
identity would disagree the first time a file is renamed.

The storage format is the decision the rest of this section rests on. A single
store, JSON or SQLite, would give faster queries and atomic multi-snippet writes,
and would cost hand-editability, comments in metadata, clean diffs,
filename-as-identity, and the ability to read your own conventions without the
tool that wrote them. The library is the user's own writing, so it stays in a
format that outlives the tool.

### 12.1 Frontmatter

| Field | Type | Meaning |
| ----- | ---- | ------- |
| title | string | what to show a person; the id is used when absent |
| description | string | one line of help |
| tags | list of strings | for filtering |
| applies_to | `agents`, `claude`, or `both` | which composed file may use it |
| stack_signals | list of strings | filenames suggesting relevance |
| category | string | a grouping label |
| order | whole number | a requested position in the composition |
| source_path | string | where extraction took a snippet's content from |
| source_heading | string | the heading the content sat under |
| imported_at | string | the date the content was extracted |

The last three are provenance, written only when a snippet was created by
extracting a section from an existing file. They are optional, so a hand-written
snippet is not second-class; informational only, so composition never reads
them; and preserved across an edit, so they do not evaporate the first time the
snippet is touched.

`applies_to` defaults to `both` when absent. A file with no frontmatter at all is
a valid snippet whose body is the whole text and whose fields all take their
defaults, so writing a snippet is no harder than writing markdown.

An unrecognized field is ignored, so a user experimenting with an extra field is
never blocked. A recognized field holding the wrong type is refused, naming the
snippet and the field, because composing the wrong thing silently is worse. This
is the same asymmetry the config uses, for the same reason.

### 12.2 Content is emitted verbatim

A snippet's body is composed into a target exactly as written. There is no
variable substitution, no templating, and no transformation of any kind.

No substitution syntax is reserved either. That matters for the future rather
than the present: a snippet containing brace sequences today must not change
meaning if templating is ever added, so the addition has to be an opt-in
frontmatter flag rather than a reinterpretation of existing snippets.

### 12.3 Ordering

`order` decides position. Snippets carrying one come first, ascending. Snippets
without one come last. A tie, and the unordered group, keep the order they were
selected in.

Unordered snippets sort last rather than at some default value. If they defaulted
to a middle value, adding an `order` to one snippet would silently rearrange
every other snippet in the file.

### 12.4 mdcompose writes only snippets into the library

Nothing but snippet markdown files is ever written into the library directory. No
index, no cache, no lock file. Any such artifact belongs in the config directory
instead.

An entry mdcompose did not write as a snippet is never modified or deleted: a
`.git` directory, a subdirectory, a symlink, a file with another extension. They
are skipped in silence rather than reported, because a library kept under version
control must not look broken to the tool.

This is what lets a user keep the library in git or a synced folder without
mdcompose fighting them. It is stated as a requirement because it is exactly the
rule that gets broken casually, by adding a cache to speed up a scan, and the
breakage is invisible to whoever adds it.

### 12.5 The library starts empty

mdcompose ships, generates, and seeds no snippets. A new library is empty until
the user adds to it, and every command that reads the library handles an empty
one as a normal state rather than an error. No starter content is offered.

Bundled snippets would be opinionated content the user did not write, appearing
in their personal library, which they would then have to curate. It would also
raise a versioning question the moment a bundled snippet was edited locally.

An absent library directory is an empty library. Resolving it never creates it.

## 13. The snippet commands

`snippet list` lists every snippet with its id, title and description. Filtering
by tag and by category narrows rather than widens: supplying both lists only
snippets matching both. A filter matching nothing is an empty result, not an
error. Machine-readable output is supported.

`snippet edit` opens a snippet in the user's configured editor, or replaces its
contents directly when they are supplied. The result is validated before it is
installed, so an edit that would not parse leaves the existing snippet exactly as
it was. With no editor configured and no contents supplied, it says so.

`snippet remove` deletes a snippet, confirming first. It never touches a project
that already composed that snippet: composition copies content, so a composed
file keeps working after its source snippet is gone.

`snippet adopt` saves the snippets embedded in the current project's manifest
into the library, so conventions received with a project can be reused elsewhere.

### 13.1 Adoption is always explicit

No other operation ever writes into the library. Composing a project never
adopts, because pulling a stranger's conventions into a personal library should
be a deliberate act rather than a side effect of opening their repository.

Adoption modifies no project file and no manifest.

An id that already exists locally with identical content is reported as already
present and not rewritten. Comparison is normalization-aware, so a snippet
differing only by line endings or a byte order mark counts as identical;
otherwise every cross-platform checkout would look like a library full of
conflicts.

An id that already exists with different content is a collision. Both versions
are shown and the user chooses to keep the local copy or overwrite it. Nothing
is overwritten without a decision, and a collision with no decision supplied
leaves the local copy alone.

Adopting only named ids is supported. An id the manifest does not embed is
refused, naming it and listing what is available.

## 14. Composition

Composition turns a snippet selection into the content of the two managed
blocks. Which block a snippet reaches is decided by its `applies_to`: a snippet
marked `agents` never appears in CLAUDE.md, one marked `claude` never appears in
AGENTS.md, and `both` appears in either.

Block ids are fixed: `agents-composition` in AGENTS.md, `claude-managed` in
CLAUDE.md.

### 14.1 AGENTS.md is always import-agnostic

AGENTS.md contains plain markdown and never an import directive, in either mode.
`@import` is a Claude Code mechanism that no other AGENTS.md-reading tool
resolves, so putting one there would produce a file that silently loses its
content for every other reader.

A consequence worth stating and testing: the composed AGENTS.md is byte-identical
whichever mode a project uses. Mode is a property of CLAUDE.md alone.

### 14.2 The two modes

In **import mode**, the CLAUDE.md block holds only an import directive pointing
at the AGENTS.md it is paired with, as a path relative to CLAUDE.md itself. The
composed content therefore exists in exactly one place, and the two files cannot
drift apart because there is only one copy.

If CLAUDE.md already carries that same import directive outside the managed
block, composition warns that the hand-written copy is now redundant. It is not
removed: the region outside the block belongs to the user, and only `import` and
`eject` act there.

In **copy mode**, the CLAUDE.md block holds a materialized copy of the composed
content, so the file is self-contained and needs no import resolution.

Both modes use the same block id. Mode-specific ids would leave the old block
behind on a mode switch, giving the user a second managed region they never asked
for. Reusing the id makes a switch a content replacement, which is exactly what
the managed block was built for.

### 14.3 A CLAUDE.md may import an AGENTS.md from elsewhere

In import mode the directive's target may be an AGENTS.md in another directory,
which is what lets one shared AGENTS.md serve several packages in a repository.
The directive then carries the relative path, and the referenced file is not
written by that run: it belongs to whoever composed it.

The option applies to import mode only. Copy mode materializes content and has
no reason to point anywhere, so supplying it there is refused rather than
silently ignored.

### 14.4 Mode is asked once and remembered

Precedence: an explicit mode, then whatever was recorded last time, then the
configured default, then a question. The answer is recorded, so later runs do not
re-ask.

Accepting every prompt answers the mode question too. Mode is a prompt, so a run
that says yes to everything must not then refuse for want of an answer the user
already gave.

## 15. Composing a directory

Composition operates on a target directory, defaulting to the current one. Each
target directory is independent: it holds its own manifest, and a parent's
recorded selections and mode are never consulted when composing a subdirectory.

Inheriting from a parent would create a silent coupling, where editing the root's
composition changed what a package composed without that package being touched.
Independence keeps each manifest a complete description of its own directory.

That is how a repository with several packages is handled: compose each one.

When the target directory has no AGENTS.md, no CLAUDE.md, and no manifest,
composition still proceeds, because a first run in a fresh project looks the
same, but it first warns that it is about to create both files there. This
catches a run started in the wrong directory before two files are written into
it in silence.

### 15.1 Stack signals

Snippets declare filenames that suggest they are relevant. Composition checks
whether those files exist in the target directory, and pre-checks the matching
snippets.

Presence only. Nothing is parsed, executed, or read. The moment an implementation
read a dependency manifest to work out a framework it would inherit every version
of that format, and repo-scanning generators already cover that ground. A
pre-check the user corrects costs one keystroke when it guesses wrong.

Two distinct things come out of the scan and must not be conflated: the signal
files found, which are recorded as the detected stack, and the snippet ids those
files suggest, which seed the picker. A filename is not a snippet id.

### 15.2 Selecting snippets

Precedence: an explicit list of ids, then accepting the detected set, then a
picker seeded with whatever is already recorded.

Recorded selections beat detection. A snippet the user unchecked must not be
re-checked on the next run, because a tool that argues with the user is worse
than one that guesses wrong once. Detection seeds the first run and offers
newly-relevant snippets later; it never overrides a choice.

Re-running never refuses. It reopens the picker with the recorded selections
already checked. Deselecting a snippet removes its content from the blocks and
its entry from the manifest. A re-apply option skips the picker and the mode
question entirely and re-composes from exactly what the manifest recorded, which
is the way to refresh a project's files from a script without the picker
re-adding a snippet the user had unchecked; it refuses only when there is no
manifest to re-apply from.

An unknown id is refused, naming it and listing what is available. An empty
selection is legal and writes empty blocks, with a warning that says the blocks
will be empty so the result is not a surprise. An empty library with nothing
recorded is refused: there is nothing to compose.

The picker is reached through a plain callable, so the interactive library that
implements it stays outside the core layer and a test can drive the same
interface with a stub.

### 15.3 Composing a manifest this machine did not write

When a manifest records files that are missing, or whose blocks have been
removed, the content has not been composed on this machine. That is the clone and
fork path.

There, the manifest is the authority and its embedded content is what gets
composed, so a reader with an empty library still reproduces the project. Only an
explicit snippet list overrides it. Accepting detected suggestions must not,
because the reader's library may be empty, which is the whole reason content
travels inside the manifest.

Before writing, the full content is shown and confirmation is required. This is
the trust boundary: that markdown was written by somebody else and is about to
land in a file an AI agent reads. Composing it silently would hide it at exactly
the moment it should be visible. Confirmation is not required when the files
already match the manifest, because nothing is crossing a boundary.

Composing never adopts anything into the local library.

### 15.4 Resolving drift before writing

Every managed file's drift status is checked before anything is written. A
drifted file is shown against what would replace it, and the choice is keep,
overwrite, or abort.

Keeping records the hash of what is actually there, and embeds that content in
the manifest. Both matter: recording the hash stops the same drift being reported
forever, and embedding the kept content means a clone reproduces the version the
user chose rather than the one they deliberately replaced.

Aborting writes nothing at all and exits 1. The user asked for files and got
none, which is not success.

A malformed file stops the run before anything is written, with no prompt.
Deliberately harsher than drift: with drift the boundaries are known and only the
content is unexpected, but malformed markers leave no way to tell which bytes
belong to the tool, so any write risks destroying the user's own content.

### 15.5 Writing the manifest

The manifest is written last, and only records files that were actually written.
A failure partway therefore leaves a file the implementation does not know it
wrote, which surfaces as drift on the next run: a state the tool already handles,
rather than silent divergence.

Nothing is added to any ignore file. The manifest is committed by design.

### 15.6 Global scope

The same composition applies to the global file pair: the global CLAUDE.md at its
fixed location, and the canonical global AGENTS.md whose path the user chose.

Its mode and selection are recorded in the global config rather than a manifest,
because there is no manifest for a home directory and inventing one would put
project-shaped state somewhere nobody would look for it.

A global run touches no project file and no project manifest.

## 16. No telemetry, no network

mdcompose collects, stores, and transmits nothing about the user or their
projects. No usage data, no analytics, no crash reports. It makes no network
request for any purpose, which also forecloses fetching snippet content from a
remote source.

There is no setting to opt out, because nothing is collected. Nothing is written
outside the files a command was asked to write.

This is stated as required behavior rather than left as an omission. The
difference matters: adding analytics or a remote fetch would mean deleting a
requirement somebody wrote deliberately, not filling a gap nobody had considered.

## 17. Sections of a markdown file

Import and convert both take an existing file apart along its headings. A section
is one heading line together with every line beneath it, down to the next heading
of the same or a higher level, or the end of the file. A section therefore
carries its nested subsections.

Sections are offered at every heading level. Selecting a parent takes its whole
subtree; selecting a subsection alone takes only that subsection, without the
parent heading; selecting a parent and one of its children applies the content
once, not twice.

Content before the first heading, and a file with no heading at all, is offered
as one section named for the file rather than discarded.

The scan is line-based and fence-aware. A line that looks like a heading but sits
inside a fenced code block is not a heading, because these files routinely
contain fenced markdown examples. This is the same rule the managed block marker
scan uses.

Extraction never transforms. Every extracted section is a verbatim slice of the
source; nothing is reflowed, and heading levels are not adjusted. The slices that
are contained in no other section tile the file exactly, so extracting them all
and rejoining reproduces the source.

A keyword filter narrows which sections are offered, matched case-insensitively
against a section's heading and its content. It never changes what is extracted:
that stays a whole section, so a selection is never an incoherent fragment. A
keyword that appears only inside a subsection surfaces both that subsection and
its parent.

## 18. Importing content from an existing file

Import reads a file from any path, inside or outside the project, and never
writes to, moves, or deletes it, including when the run fails. A missing path, a
directory, and an unreadable file are each refused by name. A source that
resolves to the same file as the target is refused.

A source on a Windows drive mounted under the WSL boundary produces the same
warning as any other path there, and the import continues.

The content a managed block holds is not offered for import, because it
originated from a snippet already available in a library. Sections before and
after a block are still offered. A source whose entire content is a managed block
has nothing to import. Malformed markers on the source stop the run.

Selected sections are applied to the project's AGENTS.md, or to CLAUDE.md when
the target option says so. They are appended at the end of the file, outside
every managed block, in the region the user owns. A later composition run neither
overwrites nor removes them. The target's managed block is byte-identical
afterwards, and its recorded hash still matches, so a health check stays clean. A
target that does not exist is created holding only the imported content, with no
managed block.

Selecting nothing modifies no file and is not an error. Naming a section absent
from the source is an error.

### 18.1 Saving an import as a snippet

Import can also write the extracted content to the library under a supplied name,
which becomes the snippet's id and filename. The snippet's title is taken from
the source heading; its category and tags come from options, because the file has
no source for them; its provenance fields record where the content came from.
Saving does not replace applying: the content reaches both the library and the
project target. Multiple selected sections concatenate in source order into one
snippet. An unusable name is refused before anything is written.

A name already in the library is handled by content: an identical body is
reported as already present and nothing is rewritten, comparison being
normalization-aware so a line-ending difference is still identical. A different
body shows both versions and offers to keep, overwrite, or save under a new name;
keeping still applies the content to the project target. An option supplies the
choice for an unattended run.

## 19. Converting content between the project pair

Convert moves content a user wrote into the wrong one of the two files. It
operates only on content outside managed blocks: it never reads a block as
convertible content and never alters one. This is the division that keeps convert
and composition from overlapping. Composition owns managed blocks; import and
convert own the regions around them; neither writes the other's territory.

Source and target must both be the project's own AGENTS.md or CLAUDE.md, and must
differ. Any other file, a missing source, and source equal to target are each
refused. A source whose entire content is a managed block has nothing to convert
and is not an error.

Every run shows a unified diff of every change to both files, the removal from
the source and the addition to the target, and requires confirmation before
writing. An option supplies the confirmation but never suppresses the diff, so an
unattended run still records what changed. Declining leaves both files unmodified.

The target is written before the source is changed. If the target write fails the
source is byte-identical to what it was, so content is never lost, only left
un-moved. Only the selected sections leave the source; unconverted sections stay
exactly as they were. A source reduced to only its managed block keeps that block
and is not deleted. Converted content lands outside the target's managed block
and survives a later composition run, adding no snippet to the manifest.

### 19.1 Mode when creating a CLAUDE.md block

A mode option applies in exactly one situation: the target is CLAUDE.md and has
no managed block yet, so convert must create one and needs to know whether it
holds an import directive or materialized content. The mode is chosen from an
explicit option, then the recorded project mode, then the configured default,
then a question, then a refusal naming the option. The chosen mode is recorded.

Everywhere else the option is refused rather than ignored: on AGENTS.md, which is
always plain markdown, and on a CLAUDE.md that already has a block, where a mode
change is composition's job. A flag that silently does nothing teaches the wrong
model.

---

## 20. Ejecting a project

Ejecting is the end of the lifecycle composition starts. It takes the managed
block markers back out of a target's files and deletes its manifest. It succeeds
from every state the rest of the tool can leave a project in, and it never
touches the snippet library: ejecting a project is not uninstalling mdcompose.

The markers are removed and the blank lines they occupied are collapsed, so the
result reads as hand-written and a second eject of the same file changes
nothing. Line endings are preserved. By default the block's former content stays
behind as plain markdown, so an import-mode CLAUDE.md keeps its bare import
directive and a composed AGENTS.md keeps its conventions. A strip option removes
the content along with the markers, for a user who wants the files as they were
before. Under either, content outside the block, a hand-written note or anything
`import` or `convert` added, is byte-identical afterwards. A file whose only
content was one block becomes empty rather than being deleted.

The manifest is deleted. It is a committed file, so the eject shows up as a
deletion in the user's next diff and is recoverable through version control;
that is the safety net, and no backup file is written.

Every change to every file, and the manifest deletion named explicitly, is shown
as a diff before anything is modified, and confirmation is required. A flag
supplies the confirmation without suppressing the diff. Declining leaves
everything unmodified. Running eject on a directory that is not managed is not a
failure and exits 0.

### 20.1 The states an eject handles

- A **drifted** block ejects with no prompt. Nothing is being overwritten: the
  content is kept or stripped, and both are what the user just asked for.
- A **malformed** block stops the run before any file is touched and before the
  manifest is deleted, because the tool cannot tell which bytes it owns. The
  user fixes one file rather than a half-ejected directory.
- A **manifest-recorded file that no longer exists** is reported and skipped;
  the run continues.
- A **manifest with no markers found** still has its manifest deleted.
- **Markers with no manifest** are still removed.

### 20.2 Global scope

`eject --global` removes the markers from the global file pair and clears the
mode and composition the global config recorded for it. Unrelated preferences,
the snippet library path among them, are left alone, and no project file or
manifest is touched.

## 21. Registered global targets

There is no universal location for a global AGENTS.md: Claude Code reads one
file, Codex another, other tools differ. A user registers each tool's location
once, and the canonical global AGENTS.md content is projected into all of them.

The flow is one-directional. The file named by `global_agents_path` is the only
source. A target is never read as a source, and there is no reverse path, so
every conflict resolves the same way: a target edited directly is reported out
of sync rather than having its edit propagate.

Registration records a preference and writes nothing at the path. Each target
carries a label and an absolute path, both unique across the set. A path that is
a directory, or that equals the canonical file, is refused. Nothing is detected:
every target is a path the user typed. The `/mnt/` boundary warning fires for a
target there, and the registration still happens.

Removing a target unregisters it and leaves its file exactly where it is,
reporting that it was left and how to delete it by hand. The file may be another
tool's only configuration; mdcompose does not own it.

The `registered_global_targets` config field holds the set. It is not settable
through `config set`, because its uniqueness and absoluteness rules cannot be
enforced from one key and value; the target commands own it, and `config show`
still displays it.

### 21.1 Projection

When the global pair is written, the canonical AGENTS.md content is written into
a managed block inside each registered target. Projection is always materialized
content, never an import directive, because no other tool resolves Claude Code's
`@import`; a target whose recorded mode is `import` is refused rather than
silently projected empty. A target file that does not exist is created holding
only its managed block. Content outside the block is preserved.

Projection is idempotent: a second write with unchanged content leaves every
target byte-identical and reports no change. Line endings are preserved.

Failures are isolated. An unwritable path, a malformed block, or a drift the
caller did not resolve skips that one target, is reported by label, and the run
exits with a non-zero code so the condition is not swallowed; every other target
is still projected.

### 21.2 Doctor and eject

`doctor` reports every registered target with its path, presence, and sync
status, and exits non-zero when any target is out of sync, missing, malformed,
or when the canonical file is unset while targets are registered.

`eject --global` removes the managed block from every registered target as well
as from the global pair, keeping the content as plain markdown by default and
removing it with the strip option. The registrations themselves are kept: a
later global write restores the projection without re-registering.

## Not yet specified

Nothing. Every planned behavior for v1 is implemented and described above:
`doctor`, `init` and `init --global`, `snippet list`, `snippet edit`,
`snippet remove`, `snippet adopt`, `import`, `convert`, `config show`,
`config set`, `config unset`, `config edit`, `eject` and `eject --global`, and
`target add`, `target list`, `target remove`.
