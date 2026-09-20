import { readDocument } from "./exit.ts";
import {
  readHealth,
  readSkillList,
  readSnippetList,
  type HealthReport,
  type LibraryReport,
} from "./reports.ts";
import type { Failure, Result } from "./result.ts";
import type { RunResult } from "./run.ts";
import { fail, ok } from "./result.ts";

// A project's health as the command line reports it, plus whether it flagged a
// condition (exit code 1). The report is kept even then: exit 1 carries a
// complete document, so it is a report of a condition, not a failure.
export interface HealthState {
  report: HealthReport;
  attention: boolean;
}

export interface Commands {
  snippetList: () => Promise<Result<LibraryReport, Failure>>;
  skillList: () => Promise<Result<LibraryReport, Failure>>;
  health: () => Promise<Result<HealthState, Failure>>;
}

// `run` starts the command line with the given arguments in the right directory.
// The global JSON option goes before the command.
export function createCommands(run: (args: readonly string[]) => Promise<RunResult>): Commands {
  return {
    async snippetList() {
      const document = readDocument(await run(["--json", "snippet", "list"]));
      return document.ok ? readSnippetList(document.value.value) : document;
    },
    async skillList() {
      const document = readDocument(await run(["--json", "skill", "list"]));
      return document.ok ? readSkillList(document.value.value) : document;
    },
    async health() {
      const document = readDocument(await run(["--json", "doctor"]));
      if (!document.ok) return fail(document.error);
      const report = readHealth(document.value.value);
      if (!report.ok) return report;
      return ok({ report: report.value, attention: document.value.attention });
    },
  };
}
