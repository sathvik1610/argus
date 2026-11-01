from __future__ import annotations

from evaluation.scenario import Scenario

RENAME_AND_DOCS = Scenario(
    id="clean_rename_and_docs",
    kind="clean",
    description="Clearer variable names and a docstring. Behavior is unchanged.",
    base_files={
        "utils.py": (
            "def total_price(items):\n"
            "    t = 0\n"
            "    for i in items:\n"
            '        t += i["price"]\n'
            "    return t\n"
        )
    },
    pr_files={
        "utils.py": (
            "def total_price(items):\n"
            '    """Return the sum of all item prices."""\n'
            "    total = 0\n"
            "    for item in items:\n"
            '        total += item["price"]\n'
            "    return total\n"
        )
    },
)

ADDED_VALIDATION = Scenario(
    id="clean_added_validation",
    kind="clean",
    description="Adds proper input validation to create_user.",
    base_files={"signup.py": "def create_user(name, age):\n    return {'name': name, 'age': age}\n"},
    pr_files={
        "signup.py": (
            "def create_user(name, age):\n"
            "    if not isinstance(name, str) or not name.strip():\n"
            '        raise ValueError("name must be a non-empty string")\n'
            "    if not isinstance(age, int) or age < 0 or age > 150:\n"
            '        raise ValueError("age must be an integer between 0 and 150")\n'
            "    return {'name': name.strip(), 'age': age}\n"
        )
    },
)

EXTRACT_HELPER = Scenario(
    id="clean_extract_helper",
    kind="clean",
    description="Pulls duplicated count/total code into a helper. Behavior is unchanged.",
    base_files={
        "report.py": (
            "def summary(rows):\n"
            "    count = len(rows)\n"
            '    total = sum(r["amount"] for r in rows)\n'
            '    return f"{count} rows, total {total}"\n\n\n'
            "def detail(rows):\n"
            "    count = len(rows)\n"
            '    total = sum(r["amount"] for r in rows)\n'
            '    return f"{count} rows, total {total}, average {total / count if count else 0}"\n'
        )
    },
    pr_files={
        "report.py": (
            "def _totals(rows):\n"
            '    return len(rows), sum(r["amount"] for r in rows)\n\n\n'
            "def summary(rows):\n"
            "    count, total = _totals(rows)\n"
            '    return f"{count} rows, total {total}"\n\n\n'
            "def detail(rows):\n"
            "    count, total = _totals(rows)\n"
            '    return f"{count} rows, total {total}, average {total / count if count else 0}"\n'
        )
    },
)

CLEAN_SCENARIOS = [RENAME_AND_DOCS, ADDED_VALIDATION, EXTRACT_HELPER]
