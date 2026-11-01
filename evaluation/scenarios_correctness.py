from __future__ import annotations

from evaluation.scenario import ExpectedBug, Scenario

OFF_BY_ONE = Scenario(
    id="cor_off_by_one",
    kind="correctness",
    description="Pagination slice returns one item too many.",
    base_files={
        "pagination.py": "def page_count(total, size):\n    return (total + size - 1) // size\n"
    },
    pr_files={
        "pagination.py": (
            "def page_count(total, size):\n"
            "    return (total + size - 1) // size\n\n\n"
            "def get_page(items, page, size):\n"
            "    start = page * size\n"
            "    return items[start : start + size + 1]\n"
        )
    },
    expected=(
        ExpectedBug(
            "pagination.py",
            "start + size + 1",
            ("off-by-one", "off by one", "extra", "one more", "size + 1", "size+1", "too many"),
        ),
    ),
)

EMPTY_AVERAGE = Scenario(
    id="cor_empty_average",
    kind="correctness",
    description="average() divides by len(values) and crashes on an empty list.",
    base_files={"stats.py": "def total(values):\n    return sum(values)\n"},
    pr_files={
        "stats.py": (
            "def total(values):\n"
            "    return sum(values)\n\n\n"
            "def average(values):\n"
            "    return sum(values) / len(values)\n"
        )
    },
    expected=(
        ExpectedBug(
            "stats.py", "sum(values) / len(values)", ("empty", "zero", "division", "zerodivision")
        ),
    ),
)

CENTS_VS_DOLLARS = Scenario(
    id="cor_cents_vs_dollars",
    kind="correctness",
    description="Free-shipping check compares a total in cents against 50 (meant as dollars).",
    base_files={
        "pricing.py": (
            "def calculate_total(order):\n"
            '    """Return the order total in CENTS (integer)."""\n'
            '    return sum(item["price_cents"] * item["qty"] for item in order["items"])\n'
        ),
        "shipping.py": (
            "def shipping_fee(order_total_cents):\n"
            "    return 499 if order_total_cents < 5000 else 0\n"
        ),
    },
    pr_files={
        "shipping.py": (
            "from pricing import calculate_total\n\n\n"
            "def shipping_fee(order_total_cents):\n"
            "    return 499 if order_total_cents < 5000 else 0\n\n\n"
            "def needs_free_shipping(order):\n"
            "    total = calculate_total(order)\n"
            "    return total >= 50  # free shipping from $50\n"
        )
    },
    expected=(
        ExpectedBug(
            "shipping.py", "return total >= 50", ("cents", "dollar", "unit", "5000", "$50")
        ),
    ),
    needs_context=True,
)

RETURN_TYPE_CHANGE = Scenario(
    id="cor_return_type_change",
    kind="correctness",
    description="parse_config now returns a dict, but app.py still unpacks a (host, port) tuple.",
    base_files={
        "config.py": (
            "def parse_config(path):\n"
            '    """Return (host, port) from a simple host:port file."""\n'
            "    with open(path) as handle:\n"
            '        host, port = handle.read().strip().split(":")\n'
            "    return host, int(port)\n"
        ),
        "app.py": (
            "from config import parse_config\n\n\n"
            "def start(path):\n"
            "    host, port = parse_config(path)\n"
            '    print(f"listening on {host}:{port}")\n'
        ),
    },
    pr_files={
        "config.py": (
            "def parse_config(path):\n"
            '    """Return a dict with host and port from a simple host:port file."""\n'
            "    with open(path) as handle:\n"
            '        host, port = handle.read().strip().split(":")\n'
            '    return {"host": host, "port": int(port)}\n'
        )
    },
    expected=(
        ExpectedBug(
            "config.py",
            'return {"host": host',
            ("caller", "unpack", "tuple", "return type", "breaking", "app.py", "backward"),
        ),
    ),
    needs_context=True,
)

CORRECTNESS_SCENARIOS = [OFF_BY_ONE, EMPTY_AVERAGE, CENTS_VS_DOLLARS, RETURN_TYPE_CHANGE]
