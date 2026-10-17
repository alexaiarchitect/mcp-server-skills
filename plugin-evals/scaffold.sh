#!/usr/bin/env bash
# Prepare the eval session's working directory.
#
#   scaffold.sh [<fixture>|none] [<mutation>] [stage-spec] [stage-server]
#
# Fixtures live in tests/fixtures/projects/ and use a fictional library
# ("bookshelf") domain, so a case can exercise a real-looking project without
# touching the repository. `none` copies no project.
#
# A mutation plants a specific defect the case's prompt or graders rely on:
#   no-prm       remove the Protected Resource Metadata route and builder
#                (ts_v1_lambda): the auth review must report AUT002
#   pin          write .mcp-spec-pin with 2026-07-28
#
# Staging directives copy read-only fixture data into ./fixtures/ inside the
# sandbox, so prompts use sandbox-relative paths:
#   stage-spec    tests/fixtures/spec/versioning-synthetic-newer.html -> ./fixtures/versioning.html
#                 (SYNTHETIC: revision 2027-03-30 does not exist)
#   stage-server  tests/fixtures/servers/fake_mcp.py -> ./fixtures/fake_mcp.py
#
# It also writes ./.scaffold/: manifest.txt records what ran, protected.sha256
# the checksum of every file a case must not modify.
#
# Requires `claude plugin eval --scaffold`; scaffold scripts are opt-in.
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fixture=""
mutation=""
stage_spec=0
stage_server=0
for arg in "$@"; do
  case "${arg}" in
    stage-spec)   stage_spec=1 ;;
    stage-server) stage_server=1 ;;
    *)
      if [[ -z "${fixture}" ]]; then fixture="${arg}"
      elif [[ -z "${mutation}" ]]; then mutation="${arg}"
      else echo "unexpected argument: ${arg}" >&2; exit 2
      fi
      ;;
  esac
done
fixture="${fixture:-ts_v1_lambda}"
mutation="${mutation:-none}"

if [[ "${fixture}" != "none" ]]; then
  source_dir="${plugin_root}/tests/fixtures/projects/${fixture}"
  if [[ ! -d "${source_dir}" ]]; then
    echo "no such fixture project: ${fixture}" >&2
    exit 2
  fi
  cp -R "${source_dir}/." .
fi

case "${mutation}" in
  none) ;;
  no-prm)
    python3 - <<'PY'
import pathlib, re
handler = pathlib.Path("apps/mcp-server/src/handler.ts")
text = handler.read_text()
text = re.sub(r'  if \(method === "GET" && path === "/\.well-known/oauth-protected-resource/mcp"\) \{.*?\n  \}\n', "", text, flags=re.S)
text = text.replace("protectedResourceMetadata, ", "")
text = text.replace('const metadataUrl = "https://mcp.bookshelf.example/.well-known/oauth-protected-resource/mcp";\n', "")
text = text.replace("wwwAuthenticate(metadataUrl)", '"Bearer"')
handler.write_text(text)
auth = pathlib.Path("packages/auth/src/index.ts")
text = auth.read_text()
text = re.sub(r"export function protectedResourceMetadata.*?\n}\n\n", "", text, flags=re.S)
text = re.sub(r"export function wwwAuthenticate.*?\n}\n", "", text, flags=re.S)
auth.write_text(text)
PY
    ;;
  pin)
    printf '2026-07-28\n' > .mcp-spec-pin
    ;;
  *)
    echo "unknown mutation: ${mutation}" >&2
    exit 2
    ;;
esac

staged=""
if [[ "${stage_spec}" -eq 1 ]]; then
  mkdir -p ./fixtures
  cp "${plugin_root}/tests/fixtures/spec/versioning-synthetic-newer.html" ./fixtures/versioning.html
  staged="${staged} spec"
fi
if [[ "${stage_server}" -eq 1 ]]; then
  mkdir -p ./fixtures
  cp "${plugin_root}/tests/fixtures/servers/fake_mcp.py" ./fixtures/fake_mcp.py
  staged="${staged} server"
fi

mkdir -p .scaffold
{
  echo "fixture=${fixture}"
  echo "mutation=${mutation}"
  echo "staged=${staged# }"
} > .scaffold/manifest.txt

: > .scaffold/protected.sha256
for protected in apps/mcp-server/src/handler.ts apps/mcp-server/src/server.ts apps/mcp-server/package.json \
                 pnpm-workspace.yaml packages/auth/src/index.ts addon.json server.py; do
  if [[ -f "${protected}" ]]; then
    python3 - "${protected}" >> .scaffold/protected.sha256 <<'PY'
import hashlib, sys
path = sys.argv[1]
print(f"{hashlib.sha256(open(path, 'rb').read()).hexdigest()}  {path}")
PY
  fi
done

echo "scaffolded ${fixture} (mutation: ${mutation}; staged:${staged:-" none"}) into $(pwd)"
