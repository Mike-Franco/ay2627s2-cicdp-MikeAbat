#!/usr/bin/env bash
# Render every Mermaid block in the repository's Markdown with the pinned
# Mermaid CLI; any syntax or render error fails the run.
set -euo pipefail

MERMAID_CLI="@mermaid-js/mermaid-cli@12.2.0"
cd "$(dirname "$0")/.."
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT
# CI runners restrict unprivileged user namespaces, which Chrome's sandbox needs.
printf '{"args":["--no-sandbox"]}\n' > "$out/puppeteer.json"

mapfile -t files < <(grep -rlF --include='*.md' '```mermaid' docs README.md CHANGELOG.md 2>/dev/null | sort)
if [ "${#files[@]}" -eq 0 ]; then
    echo "No Mermaid diagrams found."
    exit 0
fi
for file in "${files[@]}"; do
    echo "Rendering $file"
    npx --yes "$MERMAID_CLI" --quiet -p "$out/puppeteer.json" -i "$file" -o "$out/$(echo "$file" | tr '/' '_')"
done
echo "Rendered Mermaid diagrams in ${#files[@]} file(s)."
