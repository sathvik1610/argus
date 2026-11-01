from __future__ import annotations

from evaluation.scenario import ExpectedBug, Scenario

SQL_INJECTION = Scenario(
    id="sec_sql_injection",
    kind="security",
    description="New lookup builds an SQL query with an f-string from user input.",
    base_files={
        "users.py": (
            "import sqlite3\n\n\n"
            "def get_user(conn, user_id):\n"
            '    cur = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))\n'
            "    return cur.fetchone()\n"
        )
    },
    pr_files={
        "users.py": (
            "import sqlite3\n\n\n"
            "def get_user(conn, user_id):\n"
            '    cur = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))\n'
            "    return cur.fetchone()\n\n\n"
            "def find_by_name(conn, name):\n"
            "    query = f\"SELECT id, name FROM users WHERE name = '{name}'\"\n"
            "    cur = conn.execute(query)\n"
            "    return cur.fetchall()\n"
        )
    },
    expected=(
        ExpectedBug(
            "users.py",
            "SELECT id, name FROM users WHERE name",
            (
                "sql injection",
                "injection",
                "parameteriz",
                "f-string",
                "string formatting",
                "concatenat",
            ),
        ),
    ),
)

PATH_TRAVERSAL = Scenario(
    id="sec_path_traversal",
    kind="security",
    description="New download helper joins a user-supplied filename onto the upload folder.",
    base_files={
        "files.py": (
            "import os\n\n"
            'UPLOAD_DIR = "/srv/app/uploads"\n\n\n'
            "def list_uploads():\n"
            "    return sorted(os.listdir(UPLOAD_DIR))\n"
        )
    },
    pr_files={
        "files.py": (
            "import os\n\n"
            'UPLOAD_DIR = "/srv/app/uploads"\n\n\n'
            "def list_uploads():\n"
            "    return sorted(os.listdir(UPLOAD_DIR))\n\n\n"
            "def read_upload(filename):\n"
            "    path = os.path.join(UPLOAD_DIR, filename)\n"
            '    with open(path, "rb") as handle:\n'
            "        return handle.read()\n"
        )
    },
    expected=(
        ExpectedBug(
            "files.py",
            "path = os.path.join(UPLOAD_DIR, filename)",
            ("traversal", "../", "basename", "outside", "arbitrary file", "sanitiz", "validat"),
        ),
    ),
)

MISSING_AUTH = Scenario(
    id="sec_missing_auth",
    kind="security",
    description="New admin handler forgets the @require_admin decorator every other handler uses.",
    base_files={
        "auth.py": (
            "def require_admin(handler):\n"
            "    def wrapper(request):\n"
            "        if not request.user or not request.user.is_admin:\n"
            '            return {"status": 403, "error": "forbidden"}\n'
            "        return handler(request)\n\n"
            "    return wrapper\n"
        ),
        "store.py": "USERS = {}\n",
        "admin.py": (
            "from auth import require_admin\n"
            "from store import USERS\n\n\n"
            "@require_admin\n"
            "def list_users(request):\n"
            '    return {"status": 200, "users": list(USERS)}\n\n\n'
            "@require_admin\n"
            "def reset_password(request):\n"
            '    USERS[request.params["id"]]["password"] = None\n'
            '    return {"status": 200}\n'
        ),
    },
    pr_files={
        "admin.py": (
            "from auth import require_admin\n"
            "from store import USERS\n\n\n"
            "@require_admin\n"
            "def list_users(request):\n"
            '    return {"status": 200, "users": list(USERS)}\n\n\n'
            "@require_admin\n"
            "def reset_password(request):\n"
            '    USERS[request.params["id"]]["password"] = None\n'
            '    return {"status": 200}\n\n\n'
            "def delete_user(request):\n"
            '    USERS.pop(request.params["id"], None)\n'
            '    return {"status": 200}\n'
        )
    },
    expected=(
        ExpectedBug(
            "admin.py",
            "def delete_user",
            (
                "require_admin",
                "authoriz",
                "authenticat",
                "access control",
                "permission",
                "unauthenticated",
            ),
        ),
    ),
    needs_context=True,
)

HARDCODED_SECRET = Scenario(
    id="sec_hardcoded_secret",
    kind="security",
    description="A payment API key is committed as a string literal.",
    base_files={
        "settings.py": (
            "import os\n\n"
            'DEBUG = os.environ.get("DEBUG", "0") == "1"\n'
            'DATABASE_URL = os.environ["DATABASE_URL"]\n'
        )
    },
    pr_files={
        "settings.py": (
            "import os\n\n"
            'DEBUG = os.environ.get("DEBUG", "0") == "1"\n'
            'DATABASE_URL = os.environ["DATABASE_URL"]\n'
            'PAYMENT_API_KEY = "prod-payment-key-1234567890abcdef"\n'
        )
    },
    expected=(
        ExpectedBug(
            "settings.py",
            "PAYMENT_API_KEY =",
            ("hardcoded", "hard-coded", "secret", "credential", "api key", "environment variable"),
        ),
    ),
)

SECURITY_SCENARIOS = [SQL_INJECTION, PATH_TRAVERSAL, MISSING_AUTH, HARDCODED_SECRET]
