import { accessSync, constants, statSync } from "node:fs";
import { extname, posix, win32 } from "node:path";

export const EXECUTABLE_NAME = "mdcompose";
export const SETTING_NAME = "mdcompose.executablePath";

// What a path turned out to be. Only "ok" can be run.
export type Inspection = "ok" | "missing" | "not-a-file" | "not-executable";

export interface LocateOptions {
  // The user's explicit choice from user or machine settings, if any.
  setting: string | undefined;
  env: NodeJS.ProcessEnv;
  platform: NodeJS.Platform;
  inspect: (path: string) => Inspection;
}

export type Located =
  | { kind: "found"; path: string; source: "setting" | "search-path" }
  | { kind: "not-found"; checked: { setting: string | undefined; searchDirectories: string[] } }
  | { kind: "setting-unusable"; path: string; reason: string };

// Windows can start only real executables without a shell. A .cmd or .bat shim
// needs one, and the runner never uses one, so shims are not candidates.
const WINDOWS_EXTENSIONS = [".exe", ".com"];

export function searchDirectories(env: NodeJS.ProcessEnv, platform: NodeJS.Platform): string[] {
  // Windows spells the variable with any capitalisation.
  const key = Object.keys(env).find((name) => name.toLowerCase() === "path");
  const raw = key === undefined ? "" : (env[key] ?? "");
  // The separator follows the platform being asked about, not the host running
  // the code, so the rules can be tested for either from either.
  const separator = platform === "win32" ? ";" : ":";
  return raw
    .split(separator)
    .map((directory) => directory.trim().replace(/^"(.*)"$/, "$1"))
    .filter((directory) => directory !== "");
}

function candidatesIn(directory: string, platform: NodeJS.Platform): string[] {
  if (platform === "win32") {
    return WINDOWS_EXTENSIONS.map((extension) =>
      win32.join(directory, EXECUTABLE_NAME + extension),
    );
  }
  return [posix.join(directory, EXECUTABLE_NAME)];
}

const REASONS: Record<Exclude<Inspection, "ok">, string> = {
  missing: "it does not exist",
  "not-a-file": "it is not a file",
  "not-executable": "it cannot be run as a program",
};

// A setting wins outright: when it is set and unusable, the search path is not
// consulted, so a typo is reported instead of quietly running something else.
export function locateExecutable(options: LocateOptions): Located {
  const setting = options.setting?.trim();
  if (setting !== undefined && setting !== "") {
    const inspection = options.inspect(setting);
    if (inspection === "ok") return { kind: "found", path: setting, source: "setting" };
    return { kind: "setting-unusable", path: setting, reason: REASONS[inspection] };
  }
  const directories = searchDirectories(options.env, options.platform);
  for (const directory of directories) {
    for (const candidate of candidatesIn(directory, options.platform)) {
      if (options.inspect(candidate) === "ok") {
        return { kind: "found", path: candidate, source: "search-path" };
      }
    }
  }
  return { kind: "not-found", checked: { setting: undefined, searchDirectories: directories } };
}

// The real filesystem check, kept apart so the rules above can be tested with a
// fake one.
export function inspectPath(
  path: string,
  platform: NodeJS.Platform = process.platform,
): Inspection {
  let isFile: boolean;
  try {
    isFile = statSync(path).isFile();
  } catch {
    return "missing";
  }
  if (!isFile) return "not-a-file";
  if (platform === "win32") {
    return WINDOWS_EXTENSIONS.includes(extname(path).toLowerCase()) ? "ok" : "not-executable";
  }
  try {
    accessSync(path, constants.X_OK);
  } catch {
    return "not-executable";
  }
  return "ok";
}

// The message shown when nothing usable was found. Both places are named.
export function describeLocateFailure(located: Exclude<Located, { kind: "found" }>): string {
  if (located.kind === "setting-unusable") {
    return `The path in the ${SETTING_NAME} setting cannot be used: ${located.path} (${located.reason}).`;
  }
  const count = located.checked.searchDirectories.length;
  return (
    `mdcompose was not found. Checked the ${SETTING_NAME} setting (not set) and the ` +
    `executable search path (${count} ${count === 1 ? "directory" : "directories"}).`
  );
}
