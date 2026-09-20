// Command line versions are PEP 440 strings such as "0.3.0" or "0.4.0a1". The
// comparison uses the numeric release segment only, and treats any suffix as a
// pre-release of that release, which sorts just below it.

export interface Version {
  release: number[];
  preRelease: boolean;
}

export function parseVersion(text: string): Version | null {
  const match = /^\s*v?(\d+(?:\.\d+)*)([\s\S]*)$/.exec(text);
  if (match === null) return null;
  const release = (match[1] ?? "").split(".").map(Number);
  const rest = (match[2] ?? "").trim();
  return { release, preRelease: rest !== "" };
}

export function compareVersions(a: Version, b: Version): number {
  const length = Math.max(a.release.length, b.release.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (a.release[index] ?? 0) - (b.release[index] ?? 0);
    if (difference !== 0) return difference;
  }
  if (a.preRelease !== b.preRelease) return a.preRelease ? -1 : 1;
  return 0;
}

export type Compatibility =
  | { kind: "ok" }
  | { kind: "too-old"; installed: string; minimum: string }
  | { kind: "newer-than-tested"; installed: string; highestTested: string }
  | { kind: "unreadable"; output: string };

// Below the minimum the reports may lack fields the extension needs, so the
// extension refuses to run. Above the highest tested version it still runs and
// warns once.
export function checkCompatibility(
  installedOutput: string,
  minimum: string,
  highestTested: string,
): Compatibility {
  const installed = parseVersion(installedOutput);
  const lowest = parseVersion(minimum);
  const highest = parseVersion(highestTested);
  if (installed === null || lowest === null || highest === null) {
    return { kind: "unreadable", output: installedOutput.trim() };
  }
  const text = installedOutput.trim();
  if (compareVersions(installed, lowest) < 0) {
    return { kind: "too-old", installed: text, minimum };
  }
  if (compareVersions(installed, highest) > 0) {
    return { kind: "newer-than-tested", installed: text, highestTested };
  }
  return { kind: "ok" };
}
