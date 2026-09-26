#!/usr/bin/env bash
# Render every docs/diagrams/src/*.mmd to SVG and PNG in docs/diagrams/img/.
# Stops at the first diagram that fails, naming it. Safe to re-run.
#
#   docs/diagrams/render_diagrams.sh            # all diagrams
#   docs/diagrams/render_diagrams.sh 03-data    # only sources whose name starts with this
#
# Uses the Mermaid CLI through npx (Node required). If its bundled browser
# can't be downloaded, set PUPPETEER_CONFIG to a JSON file containing
# {"executablePath": "<path to Chrome>"}.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/src"; img="$here/img"
mkdir -p "$img"
extra=()
if [[ -n "${PUPPETEER_CONFIG:-}" ]]; then extra=(-p "$PUPPETEER_CONFIG"); fi
shopt -s nullglob
files=("$src"/${1:-}*.mmd)
if (( ${#files[@]} == 0 )); then echo "no .mmd files match in $src" >&2; exit 1; fi
for f in "${files[@]}"; do
  name="$(basename "$f" .mmd)"
  for fmt in svg png; do
    args=(-i "$f" -o "$img/$name.$fmt" -b white)
    [[ $fmt == png ]] && args+=(-w 1600 -s 2)
    if ! npx -y -p @mermaid-js/mermaid-cli mmdc "${args[@]}" ${extra[@]+"${extra[@]}"} >/dev/null 2>"$img/.err"; then
      echo "FAILED: $name.$fmt" >&2; cat "$img/.err" >&2; rm -f "$img/.err"; exit 1
    fi
  done
  echo "rendered $name"
done
rm -f "$img/.err"
