from dataclasses import dataclass
from datetime import datetime
from .database import Database

@dataclass
class Attendance:
    id: int | None
    employee_id: int
    date: str
    time_in: str
    time_out: str | None
    hours: float

class AttendanceModel:
    def __init__(self, db: Database):
        self.db = db

    def add_full_shift(self, employee_id: int, date: str, time_in: str, time_out: str) -> int:
        # Validate and compute hours
        t_in = datetime.strptime(time_in, "%H:%M")
        t_out = datetime.strptime(time_out, "%H:%M")
        if t_out <= t_in:
            raise ValueError("time_out must be after time_in")
        hours = round((t_out - t_in).total_seconds() / 3600.0, 2)
        return self.db.execute(
            'INSERT INTO attendance(employee_id, date, time_in, time_out, hours) VALUES(?,?,?,?,?)',
            (employee_id, date, time_in, time_out, hours)
        )

    def clock_in(self, employee_id: int, date: str, time_in: str) -> int:
        # Prevent duplicate open shift for same date
        open_rows = self.db.query(
            'SELECT id FROM attendance WHERE employee_id=? AND date=? AND time_out IS NULL ORDER BY id DESC LIMIT 1',
            (employee_id, date)
        )
        if open_rows:
            raise ValueError("Open shift already exists for this employee and date")
        return self.db.execute(
            'INSERT INTO attendance(employee_id, date, time_in, time_out, hours) VALUES(?,?,?,?,0)',
            (employee_id, date, time_in, None)
        )

    def clock_out(self, employee_id: int, date: str, time_out: str) -> None:
        # Find last open shift
        rows = self.db.query(
            'SELECT id, time_in FROM attendance WHERE employee_id=? AND date=? AND time_out IS NULL ORDER BY id DESC LIMIT 1',
            (employee_id, date)
        )
        if not rows:
            raise ValueError("No open shift to clock out for this employee and date")
        rec = rows[0]
        t_in = datetime.strptime(rec['time_in'], "%H:%M")
        t_out = datetime.strptime(time_out, "%H:%M")
        if t_out <= t_in:
            raise ValueError("time_out must be after time_in")
        hours = round((t_out - t_in).total_seconds() / 3600.0, 2)
        self.db.execute(
            'UPDATE attendance SET time_out=?, hours=? WHERE id=?',
            (time_out, hours, rec['id'])
        )

    def list_for_employee(self, employee_id: int) -> list[Attendance]:
        rows = self.db.query(
            'SELECT id, employee_id, date, time_in, time_out, hours FROM attendance WHERE employee_id=? ORDER BY date, time_in',
            (employee_id,)
        )
        return [Attendance(**row) for row in rows]
