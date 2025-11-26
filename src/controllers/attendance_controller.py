from datetime import datetime
from typing import Optional
from models.database import Database

class AttendanceController:
    def __init__(self, db, view, current_user=None, payroll_service=None):
        self.db = db
        self.view = view
        self.current_user = current_user
        self.payroll_service = payroll_service

    def _resolve_target_employee(self, requested_eid: Optional[int]) -> int:
        """Resolve employee id: non-HR users are limited to their linked employee_id."""
        if getattr(self.current_user, "is_hr", False):
            if requested_eid is None:
                raise ValueError("employee id required for HR operations")
            return requested_eid
        # non-HR
        if getattr(self.current_user, "employee_id", None) is None:
            raise PermissionError("No employee linked to this user")
        # If they requested a different eid, reject
        if requested_eid is not None and requested_eid != self.current_user.employee_id:
            raise PermissionError("You can only operate on your own attendance")
        return self.current_user.employee_id

    def sign_in(self, employee_id: int, note: str = "") -> str:
        ts = datetime.now().isoformat()
        self.db.execute("INSERT INTO attendance (employee_id, event, timestamp, corrected_by_hr, note) VALUES (?, 'sign_in', ?, 0, ?)",
                        (employee_id, ts, note))
        return ts

    def sign_out(self, employee_id: int, note: str = "") -> str:
        ts = datetime.now().isoformat()
        self.db.execute("INSERT INTO attendance (employee_id, event, timestamp, corrected_by_hr, note) VALUES (?, 'sign_out', ?, 0, ?)",
                        (employee_id, ts, note))
        return ts

    def add_correction(self, employee_id: int, timestamp_iso: str, event: str = "correction", note: str = ""):
        # HR only
        if not getattr(self.current_user, "is_hr", False):
            raise PermissionError("Only HR can add corrections")
        self.db.execute("INSERT INTO attendance (employee_id, event, timestamp, corrected_by_hr, note) VALUES (?, ?, ?, 1, ?)",
                        (employee_id, event, timestamp_iso, note))
        return True

    def list_records(self, employee_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None):
        start = (start_date + "T00:00:00") if start_date else "1970-01-01T00:00:00"
        end = (end_date + "T23:59:59") if end_date else datetime.now().isoformat()
        return self.db.query("""
            SELECT a.id, a.employee_id, e.full_name, a.event, a.timestamp, a.corrected_by_hr, a.note 
            FROM attendance a
            LEFT JOIN employees e ON a.employee_id = e.id
            WHERE a.employee_id = ? AND a.timestamp BETWEEN ? AND ? 
            ORDER BY a.timestamp
        """, (employee_id, start, end))

    def compute_hours_for_day(self, employee_id: int, date_str: str):
        # compute hours from attendance table for that date
        start = f"{date_str}T00:00:00"
        end = f"{date_str}T23:59:59"
        rows = self.db.query("SELECT event, timestamp FROM attendance WHERE employee_id = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
                             (employee_id, start, end))
        from datetime import datetime as _dt
        parsed = []
        for r in rows:
            ev = r["event"]
            ts = r["timestamp"]
            try:
                dt = _dt.fromisoformat(ts)
            except Exception:
                try:
                    dt = _dt.strptime(ts, "%Y-%m-%dT%H:%M:%S")
                except Exception:
                    continue
            parsed.append((ev, dt))

        total_seconds = 0
        i = 0
        while i < len(parsed):
            if parsed[i][0] == "sign_in":
                j = i + 1
                while j < len(parsed) and parsed[j][0] != "sign_out":
                    j += 1
                if j < len(parsed):
                    delta = parsed[j][1] - parsed[i][1]
                    total_seconds += max(0, delta.total_seconds())
                    i = j + 1
                else:
                    i += 1
            else:
                i += 1

        hours = round(total_seconds / 3600.0, 2)
        regular = round(min(8.0, hours), 2)
        overtime = round(max(0.0, hours - 8.0), 2)
        return {"date": date_str, "regular_hours": regular, "overtime_hours": overtime, "total_hours": hours}

    def delete_record(self, attendance_id: int):
        if not getattr(self.current_user, "is_hr", False):
            raise PermissionError("Only HR can delete attendance records")
        self.db.execute("DELETE FROM attendance WHERE id = ?", (attendance_id,))
        return True

    def handle_attendance(self):
        view = self.view
        if view is None:
            print("No view configured")
            return

        while True:
            view.display_attendance_menu()
            ch = view.prompt_for_input("Choose (number): ").strip()
            if ch == "1":  # Sign in
                try:
                    if getattr(self.current_user, "is_hr", False):
                        eid = int(view.prompt_for_input("Employee ID: ").strip())
                    else:
                        eid = self._resolve_target_employee(None)
                except PermissionError as e:
                    view.display_error(str(e))
                    continue
                except Exception:
                    view.display_error("Invalid id")
                    continue
                note = view.prompt_for_input("Note (optional): ").strip()
                ts = self.sign_in(eid, note)
                view.display_success("Signed in")
            elif ch == "2":  # Sign out
                try:
                    if getattr(self.current_user, "is_hr", False):
                        eid = int(view.prompt_for_input("Employee ID: ").strip())
                    else:
                        eid = self._resolve_target_employee(None)
                except PermissionError as e:
                    view.display_error(str(e))
                    continue
                except Exception:
                    view.display_error("Invalid id")
                    continue
                note = view.prompt_for_input("Note (optional): ").strip()
                ts = self.sign_out(eid, note)
                view.display_success("Signed out")
                # after sign-out, trigger near-real-time payroll update for that month
                if ts and self.payroll_service:
                    try:
                        dt = datetime.fromisoformat(ts)
                    except Exception:
                        try:
                            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
                        except Exception:
                            dt = None
                    if dt:
                        try:
                            self.payroll_service.persist_for_employee(eid, dt.year, dt.month)
                        except Exception:
                            pass
            elif ch == "3":  # Correction
                try:
                    eid = int(view.prompt_for_input("Employee ID: ").strip())
                except Exception:
                    view.display_error("Invalid id")
                    continue
                ts = view.prompt_for_input("Timestamp (YYYY-MM-DDTHH:MM:SS): ").strip()
                ev = view.prompt_for_input("Event (sign_in/sign_out/correction): ").strip() or "correction"
                note = view.prompt_for_input("Note: ").strip()
                try:
                    self.add_correction(eid, ts, ev, note)
                    view.display_success("Correction added")
                except PermissionError as e:
                    view.display_error(str(e))
                except Exception as e:
                    view.display_error(f"Error: {e}")
            elif ch == "4":  # View
                try:
                    if getattr(self.current_user, "is_hr", False):
                        eid_input = view.prompt_for_input("Employee ID: ").strip()
                        if not eid_input:
                            view.display_error("Employee ID required")
                            continue
                        eid = int(eid_input)
                    else:
                        eid = self._resolve_target_employee(None)
                except ValueError:
                    view.display_error("Invalid employee ID (must be a number)")
                    continue
                except PermissionError as e:
                    view.display_error(str(e))
                    continue
                except Exception as e:
                    view.display_error(f"Error: {e}")
                    continue
                
                start = view.prompt_for_input("Start date (YYYY-MM-DD) or blank: ").strip() or None
                end = view.prompt_for_input("End date (YYYY-MM-DD) or blank: ").strip() or None
                recs = self.list_records(eid, start, end)
                view.display_attendance_records(recs)
            elif ch == "5":  # Delete
                try:
                    aid = int(view.prompt_for_input("Attendance record ID to delete: ").strip())
                except Exception:
                    view.display_error("Invalid id")
                    continue
                try:
                    self.delete_record(aid)
                    view.display_success("Deleted")
                except PermissionError as e:
                    view.display_error(str(e))
            elif ch == "6":  # Back
                break
            else:
                view.display_invalid_choice_message()
