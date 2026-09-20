// Replaces the placeholder publisher id with the real one, everywhere it appears.
//
//   node scripts/set-publisher.mjs <publisher-id>
//
// The publisher id is the same string on the Microsoft Marketplace and on Open VSX
// (Open VSX asks for the same publisher and namespace on both), so there is one
// placeholder, `publisher-tbd`, and this is the one place that replaces it. The id
// must satisfy the stricter of the two registries: lower-case letters, digits, and
// hyphens, starting with a letter or digit.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PLACEHOLDER = "publisher-tbd";
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
// Every file that may name the publisher. Add a file here if it starts to.
const FILES = ["package.json", "DEVELOPMENT.md"];

const id = process.argv[2];
if (id === undefined || !/^[a-z0-9][a-z0-9-]*$/.test(id)) {
  console.error("Usage: node scripts/set-publisher.mjs <publisher-id>");
  console.error("The id may use lower-case letters, digits, and hyphens only.");
  process.exit(1);
}

let replaced = 0;
for (const name of FILES) {
  const file = path.join(root, name);
  const before = readFileSync(file, "utf8");
  const count = before.split(PLACEHOLDER).length - 1;
  if (count > 0) {
    writeFileSync(file, before.replaceAll(PLACEHOLDER, id), "utf8");
    console.log(`${name}: replaced ${count}`);
    replaced += count;
  }
}
if (replaced === 0) console.log(`No "${PLACEHOLDER}" left to replace.`);
