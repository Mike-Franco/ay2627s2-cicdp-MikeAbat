"""Curated inventory icons (TORY-54).

Only the key is stored on an inventory. Each key is a Lucide icon
(https://lucide.dev, ISC licence, see static/tory/icons/LICENSE-lucide.txt)
compiled into one self-hosted sprite, static/tory/icons/lucide-sprite.svg, by
scripts/build_icon_sprite.py. Add an icon here, rebuild the sprite, and add a
migration for the database check constraint.
"""

ICONS = (
    ("package", "Package"),
    ("box", "Box"),
    ("archive", "Archive"),
    ("warehouse", "Warehouse"),
    ("store", "Store"),
    ("shopping-cart", "Shopping cart"),
    ("truck", "Truck"),
    ("clipboard-list", "Clipboard"),
    ("pill", "Pill"),
    ("stethoscope", "Stethoscope"),
    ("flask-conical", "Lab flask"),
    ("baby", "Baby"),
    ("refrigerator", "Refrigerator"),
    ("snowflake", "Frozen"),
    ("coffee", "Coffee"),
    ("apple", "Fruit"),
    ("wheat", "Grains"),
    ("milk", "Dairy"),
    ("beef", "Meat"),
    ("fish", "Fish"),
    ("shirt", "Clothing"),
    ("wrench", "Tools"),
    ("dog", "Pets"),
    ("sparkles", "Cleaning"),
)

ICON_KEYS = frozenset(key for key, _label in ICONS)
DEFAULT_ICON = "package"
