"""Preset colours shared by avatars (TORY-55) and inventories (TORY-54).

Only these keys are stored. Each maps to a ``tone-<key>`` class in
``static/tory/pages.css``; the page CSP allows no inline styles, so a colour is
never written into an element's ``style``. Every colour is a dark enough shade
that white text and icons on it meet WCAG AA (4.5:1) in both themes.
"""

TONES = (
    ("slate", "Slate", "#475569"),
    ("indigo", "Indigo", "#4338ca"),
    ("blue", "Blue", "#1d4ed8"),
    ("sky", "Sky", "#0369a1"),
    ("teal", "Teal", "#0f766e"),
    ("green", "Green", "#15803d"),
    ("amber", "Amber", "#b45309"),
    ("orange", "Orange", "#c2410c"),
    ("rose", "Rose", "#be123c"),
    ("purple", "Purple", "#7e22ce"),
)

TONE_CHOICES = tuple((key, label) for key, label, _hex in TONES)
TONE_KEYS = frozenset(key for key, _label, _hex in TONES)
DEFAULT_TONE = "slate"
