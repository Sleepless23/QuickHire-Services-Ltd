from dataclasses import dataclass
from typing import Optional
import hashlib

@dataclass
class User:
    id: int
    username: str
    is_hr: bool
    employee_id: Optional[int] = None
    active: bool = True

class UserModel:
    def __init__(self, db):
        self.db = db

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user by username/password.
        Returns User object if successful, None if failed.
        Prevents login if employee is inactive (deleted).
        """
        row = self.db.fetchone(
            "SELECT u.id, u.username, u.password_hash, u.is_hr, u.employee_id, u.active, COALESCE(e.active, 1) as employee_active "
            "FROM users u "
            "LEFT JOIN employees e ON u.employee_id = e.id "
            "WHERE u.username = ?",
            (username,)
        )
        
        if not row:
            return None
        
        # Check if user account is active
        if not row["active"]:
            return None
        
        # Check if linked employee is active (deleted employees have active=0)
        if row["employee_id"] and not row["employee_active"]:
            return None
        
        # Verify password
        if not self._verify_password(password, row["password_hash"]):
            return None
        
        return User(
            id=row["id"],
            username=row["username"],
            is_hr=bool(row["is_hr"]),
            employee_id=row["employee_id"],
            active=bool(row["active"])
        )

    def _verify_password(self, password: str, hash_val: str) -> bool:
        """Verify password against hash."""
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        return pwd_hash == hash_val

    def create_user(self, username: str, password: str, is_hr: bool = False, employee_id: Optional[int] = None) -> int:
        """Create a new user account."""
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        cur = self.db.execute(
            "INSERT INTO users (username, password_hash, is_hr, employee_id, active) VALUES (?, ?, ?, ?, 1)",
            (username, pwd_hash, 1 if is_hr else 0, employee_id)
        )
        return cur.lastrowid

    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        row = self.db.fetchone("SELECT id, username, password_hash, is_hr, employee_id, active FROM users WHERE id = ?", (user_id,))
        if not row:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            is_hr=bool(row["is_hr"]),
            employee_id=row["employee_id"],
            active=bool(row["active"])
        )