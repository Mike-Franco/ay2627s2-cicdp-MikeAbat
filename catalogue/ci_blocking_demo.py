"""Deliberate lint violation to demonstrate that CI blocks a pull request.

This file exists only on the demo/failing-lint-check branch and must never be merged.
"""

import os  # deliberately unused (ruff F401) so the lint gate fails


def demo():
    return "CI should block this pull request"
