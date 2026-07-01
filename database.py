import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "/data/expenses.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT NOT NULL
            )
        """)


def add_user(user_id: int, username: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_seen) VALUES (?, ?, ?)",
            (user_id, username, datetime.now().isoformat()),
        )


def add_expense(user_id: int, username: str, amount: float, category: str, note: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, username, amount, category, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, amount, category, note, datetime.now().isoformat()),
        )


def get_last_expenses(user_id: int, limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return rows


def delete_last_expense(user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM expenses WHERE id = ?", (row["id"],))
            return True
        return False


def get_monthly_report(user_id: int):
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) as total, COUNT(*) as cnt
            FROM expenses
            WHERE user_id = ? AND created_at LIKE ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id, f"{month_prefix}%"),
        ).fetchall()
        total_row = conn.execute(
            "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND created_at LIKE ?",
            (user_id, f"{month_prefix}%"),
        ).fetchone()
        return rows, (total_row["total"] or 0)


def get_global_stats():
    with get_conn() as conn:
        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        expense_count = conn.execute("SELECT COUNT(*) as c FROM expenses").fetchone()["c"]
        total_sum = conn.execute("SELECT SUM(amount) as s FROM expenses").fetchone()["s"] or 0
        top_categories = conn.execute(
            """
            SELECT category, SUM(amount) as total
            FROM expenses GROUP BY category ORDER BY total DESC LIMIT 5
            """
        ).fetchall()
        return user_count, expense_count, total_sum, top_categories
