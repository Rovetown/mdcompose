import { HIGHEST_TESTED_CLI_VERSION, MINIMUM_CLI_VERSION } from "./compat.ts";
import { mapRun } from "./exit.ts";
import {
  describeLocateFailure,
  locateExecutable,
  type Inspection,
  type Located,
} from "./locate.ts";
import type { RunResult } from "./run.ts";
import { checkCompatibility } from "./version.ts";

// Whether the extension can talk to a suitable mdcompose. Everything the views
// show depends on this, so it is resolved first and again whenever the setting
// changes or a refresh runs while it was not ready.
export type Environment =
  | { kind: "ready"; executable: string; version: string; newerThanTested: boolean }
  | { kind: "not-found"; message: string }
  | { kind: "setting-unusable"; message: string }
  | { kind: "too-old"; message: string; installed: string; minimum: string }
  | { kind: "unreadable"; message: string };

export interface EnvironmentDeps {
  setting: string | undefined;
  env: NodeJS.ProcessEnv;
  platform: NodeJS.Platform;
  inspect: (path: string) => Inspection;
  // Runs `mdcompose --version` with the given executable.
  runVersion: (executable: string) => Promise<RunResult>;
}

export async function resolveEnvironment(deps: EnvironmentDeps): Promise<Environment> {
  const located: Located = locateExecutable({
    setting: deps.setting,
    env: deps.env,
    platform: deps.platform,
    inspect: deps.inspect,
  });
  if (located.kind === "not-found") {
    return { kind: "not-found", message: describeLocateFailure(located) };
  }
  if (located.kind === "setting-unusable") {
    return { kind: "setting-unusable", message: describeLocateFailure(located) };
  }
  const run = await deps.runVersion(located.path);
  const finished = mapRun(run);
  if (!finished.ok) {
    return { kind: "unreadable", message: finished.error.message };
  }
  const output = finished.value.stdout.trim();
  const compatibility = checkCompatibility(output, MINIMUM_CLI_VERSION, HIGHEST_TESTED_CLI_VERSION);
  switch (compatibility.kind) {
    case "too-old":
      return {
        kind: "too-old",
        message:
          `mdcompose ${compatibility.installed} is older than the ${compatibility.minimum} ` +
          "this extension needs.",
        installed: compatibility.installed,
        minimum: compatibility.minimum,
      };
    case "unreadable":
      return {
        kind: "unreadable",
        message: `Could not read a version from mdcompose. It printed: ${compatibility.output}`,
      };
    case "newer-than-tested":
      return { kind: "ready", executable: located.path, version: output, newerThanTested: true };
    case "ok":
      return { kind: "ready", executable: located.path, version: output, newerThanTested: false };
  }
}
