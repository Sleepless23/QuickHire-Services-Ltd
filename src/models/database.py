from pathlib import Path
from typing import List, Any
import sqlite3
import hashlib

# Place the database file at the project root folder
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "attendance_payroll.db"

class Database:
    def __init__(self, db_path: Path | str = DB_PATH):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        # create tables if they don't exist and keep backward compatibility
        with self._connect() as conn:
            cur = conn.cursor()
            # employees first (users will reference employees)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT,
                contact TEXT,
                rate REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """)
            # users table with optional employee_id FK (may be NULL)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_hr INTEGER NOT NULL DEFAULT 0,
                employee_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                corrected_by_hr INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                amount REAL NOT NULL,
                kind TEXT,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS payroll_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                regular_hours REAL NOT NULL,
                overtime_hours REAL NOT NULL,
                hourly_rate REAL NOT NULL,
                gross_pay REAL NOT NULL,
                total_adjustments REAL NOT NULL,
                net_pay REAL NOT NULL,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """)
            # ensure users table has columns for older DBs
            cur.execute("PRAGMA table_info(users)")
            cols = [r[1] for r in cur.fetchall()]
            if "employee_id" not in cols:
                try:
                    cur.execute("ALTER TABLE users ADD COLUMN employee_id INTEGER")
                except Exception:
                    pass
            if "active" not in cols:
                try:
                    cur.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
                except Exception:
                    pass
            conn.commit()
            
            # Seed default admin account if it doesn't exist
            self._seed_admin_account(cur)
            conn.commit()

    def _seed_admin_account(self, cur: sqlite3.Cursor):
        """Create default admin account (username: admin, password: admin) if not exists."""
        # Check if admin user already exists
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        if cur.fetchone():
            return  # Admin already exists
        
        # Hash password "admin"
        admin_password = "admin"
        pwd_hash = hashlib.sha256(admin_password.encode()).hexdigest()
        
        # Insert admin user (no employee_id since admin is system user)
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, is_hr, employee_id, active) VALUES (?, ?, 1, NULL, 1)",
                ("admin", pwd_hash)
            )
        except sqlite3.IntegrityError:
            # In case of race condition, silently pass
            pass

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            conn.commit()
            return cur

    def executemany(self, query: str, seq_of_params: list[tuple]) -> sqlite3.Cursor:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.executemany(query, seq_of_params)
            conn.commit()
            return cur

    def query(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur.fetchall()

    def fetchone(self, query: str, params: tuple = ()) -> Any:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur.fetchone()
