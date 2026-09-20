// Runs inside the editor's extension host, so it is plain CommonJS.
const assert = require("node:assert");
const vscode = require("vscode");

exports.run = async function run() {
  const extension = vscode.extensions.all.find(
    (candidate) => candidate.packageJSON.name === "mdcompose",
  );
  assert.ok(extension, "the extension is loaded in the test host");
  await extension.activate();
  assert.strictEqual(extension.isActive, true, "the extension activates");
};
