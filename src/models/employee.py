from dataclasses import dataclass
from .database import Database
from typing import Optional
from datetime import datetime

@dataclass
class Employee:
    id: int | None
    full_name: str
    role: str
    rate: float
    department: Optional[str] = None
    contact: Optional[str] = None

class EmployeeModel:
    def __init__(self, db: Database):
        self.db = db

    def add(self, emp: Employee) -> int:
        # ensure active is set to 1 on creation and record created_at
        cur = self.db.execute(
            "INSERT INTO employees (full_name, role, department, contact, rate, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (emp.full_name, emp.role, emp.department, emp.contact, float(emp.rate), 1, datetime.now().isoformat())
        )
        return cur.lastrowid

    def delete(self, employee_id: int) -> None:
        # Soft-delete: mark inactive and keep history
        self.db.execute("UPDATE employees SET active = 0 WHERE id = ?", (employee_id,))

    def list(self) -> list[Employee]:
        rows = self.db.query("SELECT id, full_name, role, department, contact, rate FROM employees WHERE active = 1 ORDER BY id")
        result = []
        for r in rows:
            result.append(Employee(
                id = r["id"],
                full_name = r["full_name"],
                role = r["role"],
                rate = float(r["rate"]),
                department = r.get("department"),
                contact = r.get("contact")
            ))
        return result
