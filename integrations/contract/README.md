# Contract samples

Each `*.json` file here is a sample report produced by the real `mdcompose`
command line, run against a scratch home and configuration directory. Together
they list the fields editor integrations may rely on.

| Sample | Command |
| ------ | ------- |
| `doctor.json` | `mdcompose --json doctor` |
| `snippet-list.json` | `mdcompose --json snippet list` |
| `skill-list.json` | `mdcompose --json skill list` |
| `target-list.json` | `mdcompose --json target list` |

The samples record which fields exist, not what their values are. Paths are
replaced by `<scratch>`, and the values are from one scratch run on one
platform, so an integration must not depend on them.

## The guard

`tests/test_integration_contract.py` runs each command against a fresh scratch
environment and fails when a report no longer carries any field its sample lists.
Extra fields in a report never fail it, because integrations ignore fields they
do not know.

## Changing a sample

Removing or renaming a reported field breaks every integration, so it needs the
sample and each integration updated in the same change. To regenerate the samples
after a deliberate change, run the test suite once with
`MDCOMPOSE_WRITE_CONTRACT_FIXTURES=1` set, then review the diff.

Do not hand-edit a sample to make the test pass.
