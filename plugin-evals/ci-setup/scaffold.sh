#!/usr/bin/env bash
# Per-case entry point: `claude plugin eval` runs the script named in case.yaml from
# the case directory, in an empty workspace. All the work is in the shared script.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$here/../scaffold.sh" ts_v1_lambda
