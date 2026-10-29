"""Small dependency-free documentation checks for Tory CI.

Rules: UTF-8 Markdown, a single level-one heading as the first nonblank line,
newline at EOF, no tab characters, no merge-conflict markers, and required
project documents present. Two-space Markdown hard breaks are allowed.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
REQUIRED = (
    "README.md",
    "docs/planning/PLANNING_GATE_P1.md",
    "docs/planning/OWNER_DECISIONS.md",
    "docs/planning/PROJECT_CHARTER.md",
    "docs/decisions/ADR-001-backend-and-database.md",
    "docs/TECHNOLOGY_EVALUATION.md",
    "docs/POC_RESULTS.md",
    "docs/POC_HANDOVER.md",
    "docs/TECHNICAL_FEASIBILITY.md",
    "docs/requirements/SOFTWARE_REQUIREMENTS_SPECIFICATION.md",
    "docs/requirements/ROLE_PERMISSION_MATRIX.md",
    "docs/requirements/BUSINESS_RULES_AND_EDGE_CASES.md",
    "docs/requirements/REQUIREMENTS_TRACEABILITY_MATRIX.md",
    "docs/requirements/REQUIREMENTS_REVIEW.md",
)


def check_conflicts(path: Path, content: str) -> list[str]:
    errors = []
    for number, line in enumerate(content.splitlines(), 1):
        if (line.startswith(("<<<<<<< ", ">>>>>>> ", "||||||| "))
                or line == "======="):
            errors.append(f"{path.relative_to(ROOT)}:{number}: merge-conflict marker")
    return errors


def main() -> int:
    errors = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"{relative}: required document is missing")

    markdown = sorted([ROOT / "README.md", *(ROOT / "docs").rglob("*.md")])
    for path in markdown:
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append(f"{path.relative_to(ROOT)}: not valid UTF-8")
            continue
        errors.extend(check_conflicts(path, content))
        lines = content.splitlines()
        first = next((line for line in lines if line.strip()), "")
        if not first.startswith("# "):
            errors.append(f"{path.relative_to(ROOT)}: first nonblank line must be an H1")
        if sum(line.startswith("# ") for line in lines) != 1:
            errors.append(f"{path.relative_to(ROOT)}: expected exactly one H1")
        if not content.endswith("\n"):
            errors.append(f"{path.relative_to(ROOT)}: missing final newline")
        if "\t" in content:
            errors.append(f"{path.relative_to(ROOT)}: tab character found")

    for path in [ROOT / ".gitignore", ROOT / ".github/workflows/docs-ci.yml", ROOT / "scripts/check_docs.py"]:
        errors.extend(check_conflicts(path, path.read_text(encoding="utf-8")))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentation checks passed ({len(markdown)} Markdown files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
