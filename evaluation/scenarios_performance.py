from __future__ import annotations

from evaluation.scenario import ExpectedBug, Scenario

NESTED_DUPLICATES = Scenario(
    id="perf_nested_duplicates",
    kind="performance",
    description="Duplicate finder compares every pair with nested loops.",
    base_files={"dedupe.py": "def unique(items):\n    return list(dict.fromkeys(items))\n"},
    pr_files={
        "dedupe.py": (
            "def unique(items):\n"
            "    return list(dict.fromkeys(items))\n\n\n"
            "def find_duplicates(items):\n"
            "    duplicates = []\n"
            "    for i in range(len(items)):\n"
            "        for j in range(i + 1, len(items)):\n"
            "            if items[i] == items[j] and items[i] not in duplicates:\n"
            "                duplicates.append(items[i])\n"
            "    return duplicates\n"
        )
    },
    expected=(
        ExpectedBug(
            "dedupe.py",
            "for j in range(i + 1",
            ("quadratic", "nested loop", "o(n^2)", "o(n²)", "o(n**2)", "set", "counter"),
        ),
    ),
)

N_PLUS_ONE = Scenario(
    id="perf_n_plus_one",
    kind="performance",
    description="Fetching many orders runs one database query per id inside a loop.",
    base_files={
        "orders.py": (
            "def get_order(db, order_id):\n"
            '    return db.query("SELECT * FROM orders WHERE id = ?", (order_id,))[0]\n'
        )
    },
    pr_files={
        "orders.py": (
            "def get_order(db, order_id):\n"
            '    return db.query("SELECT * FROM orders WHERE id = ?", (order_id,))[0]\n\n\n'
            "def get_orders(db, order_ids):\n"
            "    orders = []\n"
            "    for order_id in order_ids:\n"
            '        orders.append(db.query("SELECT * FROM orders WHERE id = ?", (order_id,))[0])\n'
            "    return orders\n"
        )
    },
    expected=(
        ExpectedBug(
            "orders.py",
            "for order_id in order_ids",
            (
                "n+1",
                "single query",
                "one query",
                "batch",
                "in (",
                "round trip",
                "round-trip",
                "each id",
                "per id",
                "query per",
                "queries",
            ),
        ),
    ),
)

REREAD_CONFIG = Scenario(
    id="perf_reread_config",
    kind="performance",
    description=(
        "get_setting lost its cache and now re-reads settings.json on every call; "
        "worker.py calls it once per row."
    ),
    base_files={
        "settings_store.py": (
            "import json\n\n_CACHE = {}\n\n\n"
            "def get_setting(name):\n"
            "    if not _CACHE:\n"
            '        with open("settings.json") as handle:\n'
            "            _CACHE.update(json.load(handle))\n"
            "    return _CACHE[name]\n"
        ),
        "worker.py": (
            "from settings_store import get_setting\n\n\n"
            "def process(rows):\n"
            '    return [row * get_setting("multiplier") for row in rows]\n'
        ),
    },
    pr_files={
        "settings_store.py": (
            "import json\n\n\n"
            "def get_setting(name):\n"
            '    with open("settings.json") as handle:\n'
            "        return json.load(handle)[name]\n"
        )
    },
    expected=(
        ExpectedBug(
            "settings_store.py",
            'with open("settings.json")',
            (
                "cache",
                "every call",
                "each call",
                "re-read",
                "reread",
                "reads the file",
                "repeatedly",
                "disk",
                "worker",
                "loop",
            ),
        ),
    ),
    needs_context=True,
)

PERFORMANCE_SCENARIOS = [NESTED_DUPLICATES, N_PLUS_ONE, REREAD_CONFIG]
