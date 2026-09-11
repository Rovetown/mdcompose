# Security policy

## Reporting a vulnerability

Report a suspected vulnerability through GitHub's private vulnerability reporting at https://github.com/Rovetown/mdcompose/security/advisories/new, or open the **Security** tab of this repository and choose **Report a vulnerability**.
That channel is private to the maintainers.

Please do not open a public issue for a security problem.

Include the version, the platform, and the smallest reproduction you can.
You will get an acknowledgement within a week.

## Scope

mdcompose reads and writes Markdown files and composes them from a local snippet library.
It makes no network requests and runs no telemetry.
The security-relevant surface is:

- path handling on Windows, WSL, and POSIX (a crafted path or snippet name that escapes the intended directory);
- the managed-block and manifest parsers (input that causes an unhandled exception, a hang, or a write outside a managed block);
- the fact that composed snippet content is transported verbatim into files an AI agent reads.
  This is by design: composing from a repository means trusting its authors, the same as running its build scripts.
  mdcompose deliberately does not sanitise transported content or scan it for injection.

## Supported versions

Until 1.0, only the latest release receives fixes.
