import { spawn } from "node:child_process";

export interface RunOptions {
  executable: string;
  args: readonly string[];
  cwd: string;
  timeoutMs: number;
  // Refuse output beyond this size instead of holding it all in memory.
  maxOutputBytes?: number;
  env?: NodeJS.ProcessEnv;
}

export type RunResult =
  | { kind: "exited"; code: number; stdout: string; stderr: string }
  | { kind: "timeout"; timeoutMs: number }
  | { kind: "output-too-large"; limit: number }
  | { kind: "signalled"; signal: string }
  | { kind: "spawn-failed"; message: string };

const DEFAULT_MAX_OUTPUT_BYTES = 10 * 1024 * 1024;

// Runs one command. The arguments go to the program as a list and never through
// a shell, so a path with spaces or quotes cannot be reinterpreted. Standard
// input is closed, so a program that wanted to prompt fails instead of waiting.
export function runCommand(options: RunOptions): Promise<RunResult> {
  const limit = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES;
  return new Promise((resolve) => {
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let size = 0;
    let settled = false;
    let timer: NodeJS.Timeout | undefined;

    const finish = (result: RunResult): void => {
      if (settled) return;
      settled = true;
      if (timer !== undefined) clearTimeout(timer);
      resolve(result);
    };

    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(options.executable, [...options.args], {
        cwd: options.cwd,
        shell: false,
        // Without this, Windows opens an empty console window for the child.
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        env: { ...process.env, ...options.env },
      });
    } catch (error) {
      finish({ kind: "spawn-failed", message: String(error) });
      return;
    }

    const collect = (into: Buffer[]) => (chunk: Buffer) => {
      size += chunk.length;
      if (size > limit) {
        child.kill("SIGKILL");
        finish({ kind: "output-too-large", limit });
        return;
      }
      into.push(chunk);
    };
    child.stdout?.on("data", collect(stdout));
    child.stderr?.on("data", collect(stderr));

    child.on("error", (error) => finish({ kind: "spawn-failed", message: error.message }));
    child.on("close", (code, signal) => {
      if (code === null) {
        finish({ kind: "signalled", signal: signal ?? "unknown" });
        return;
      }
      finish({
        kind: "exited",
        code,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      });
    });

    timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish({ kind: "timeout", timeoutMs: options.timeoutMs });
    }, options.timeoutMs);
  });
}
