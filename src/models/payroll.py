from dataclasses import dataclass
from .database import Database

@dataclass
class Payroll:
    id: int | None
    employee_id: int
    period: str
    regular_hours: float
    overtime_hours: float
    gross: float
    tax: float
    net: float

class PayrollModel:
    def __init__(self, db: Database):
        self.db = db

    def add(self, pr: Payroll) -> int:
        return self.db.execute(
            'INSERT INTO payroll(employee_id, period, regular_hours, overtime_hours, gross, tax, net) VALUES(?,?,?,?,?,?,?)',
            (pr.employee_id, pr.period, pr.regular_hours, pr.overtime_hours, pr.gross, pr.tax, pr.net)
        )

    def delete_for_employee(self, employee_id: int) -> None:
        self.db.execute('DELETE FROM payroll WHERE employee_id=?', (employee_id,))

    def delete_for_period(self, period: str) -> None:
        self.db.execute('DELETE FROM payroll WHERE period=?', (period,))

    def list_for_period(self, period: str) -> list[Payroll]:
        rows = self.db.query(
            'SELECT id, employee_id, period, regular_hours, overtime_hours, gross, tax, net FROM payroll WHERE period=? ORDER BY employee_id',
            (period,)
        )
        return [Payroll(**row) for row in rows]
