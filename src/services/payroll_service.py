from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from typing import Optional, List
from datetime import datetime, timedelta
import csv

try:
    from ..models.attendance import AttendanceModel
    from ..models.payroll import Payroll, PayrollModel
    from ..models.employee import Employee
    from ..models.database import Database
except Exception:
    # robust import paths when running in different contexts
    from src.models.attendance import AttendanceModel  # type: ignore
    from src.models.payroll import Payroll, PayrollModel  # type: ignore
    from src.models.employee import Employee  # type: ignore
    from src.models.database import Database  # type: ignore

@dataclass
class TaxPolicy:
    rate: float = 0.15

class PayrollService:
    def __init__(self, db: Database, attendance_model: Optional[AttendanceModel] = None, payroll_model: Optional[PayrollModel] = None, tax_policy: Optional[TaxPolicy] = None, overtime_multiplier: float = 1.5):
        """
        db: Database instance (required)
        attendance_model/payroll_model optional wrappers (if you have specific model classes)
        """
        self.db = db
        self.attendance_model = attendance_model
        self.payroll_model = payroll_model
        self.tax_policy = tax_policy or TaxPolicy()
        self.overtime_multiplier = float(overtime_multiplier)

        # lazy-create model wrappers if not provided (models may live in your repo)
        # if AttendanceModel/PayrollModel classes are available via imports, instantiate them
        if self.attendance_model is None:
            try:
                self.attendance_model = AttendanceModel(db)  # type: ignore
            except Exception:
                self.attendance_model = None
        if self.payroll_model is None:
            try:
                self.payroll_model = PayrollModel(db)  # type: ignore
            except Exception:
                self.payroll_model = None

    def _get_employee_rate(self, employee_id: int) -> float:
        row = self.db.fetchone("SELECT rate FROM employees WHERE id = ? AND active = 1", (employee_id,))
        if not row:
            raise ValueError("Employee not found or inactive")
        return float(row["rate"])

    def _sum_adjustments(self, employee_id: int, year: int, month: int) -> float:
        row = self.db.fetchone("SELECT COALESCE(SUM(amount),0) as total FROM adjustments WHERE employee_id = ? AND year = ? AND month = ?", (employee_id, year, month))
        return float(row["total"]) if row else 0.0

    def _aggregate_hours_by_day(self, employee_id: int, period_year: int, period_month: int) -> dict:
        """
        Returns mapping date_str -> total_hours for the given month.
        Prefer attendance_model.list_for_employee if it provides per-day totals (keys/attrs 'date' and 'hours'),
        otherwise fall back to computing from the attendance table (timestamp sign_in/sign_out pairs).
        """
        day_hours = defaultdict(float)
        # Try high-level attendance model
        if self.attendance_model and hasattr(self.attendance_model, "list_for_employee"):
            try:
                items = self.attendance_model.list_for_employee(employee_id, period_year, period_month)
                # items expected to be iterable of {'date': 'YYYY-MM-DD', 'hours': X}
                for it in items:
                    d = it.get("date") if isinstance(it, dict) else getattr(it, "date", None)
                    hours = it.get("hours") if isinstance(it, dict) else getattr(it, "hours", None)
                    if d and hours is not None:
                        day_hours[d] += float(hours)
                        continue
            except Exception:
                # fall through to raw table parsing
                pass

        # Fallback: compute from attendance table sign_in/sign_out pairs
        start = f"{period_year:04d}-{period_month:02d}-01T00:00:00"
        if period_month == 12:
            end = f"{period_year+1:04d}-01-01T00:00:00"
        else:
            end = f"{period_year:04d}-{period_month+1:02d}-01T00:00:00"

        rows = self.db.query("SELECT event, timestamp FROM attendance WHERE employee_id = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
                             (employee_id, start, end))
        parsed = []
        for r in rows:
            ev = r["event"]
            ts = r["timestamp"]
            try:
                # try ISO parse first
                dt = datetime.fromisoformat(ts)
            except Exception:
                # fallback common formats
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    # ignore unparsable
                    continue
            parsed.append((ev, dt))

        # pair sign_in -> sign_out; if missing sign_out ignore that sign_in
        i = 0
        while i < len(parsed):
            ev, dt = parsed[i]
            if ev == "sign_in":
                # find next sign_out
                j = i + 1
                while j < len(parsed) and parsed[j][0] != "sign_out":
                    j += 1
                if j < len(parsed) and parsed[j][0] == "sign_out":
                    dt_out = parsed[j][1]
                    # if sign_out earlier than sign_in skip
                    if dt_out > dt:
                        duration = (dt_out - dt).total_seconds() / 3600.0
                        day_key = dt.date().isoformat()
                        day_hours[day_key] += duration
                    i = j + 1
                else:
                    # no sign_out found -> skip this sign_in
                    i += 1
            else:
                # stray sign_out with no preceding sign_in -> ignore
                i += 1

        return dict(day_hours)

    def compute_for_employee(self, employee_id: int, year: int, month: int, hourly_rate: Optional[float] = None) -> dict:
        """
        Compute payroll for employee for given year/month.
        If hourly_rate not provided, read from employees table.
        Returns a dict with payroll data.
        """
        if hourly_rate is None:
            hourly_rate = self._get_employee_rate(employee_id)

        # Get employee name
        emp_row = self.db.fetchone("SELECT full_name FROM employees WHERE id = ? AND active = 1", (employee_id,))
        if not emp_row:
            raise ValueError(f"Employee {employee_id} not found or inactive")
        full_name = emp_row["full_name"]

        day_hours = self._aggregate_hours_by_day(employee_id, year, month)
        regular_hours = sum(min(8.0, h) for h in day_hours.values())
        overtime_hours = sum(max(0.0, h - 8.0) for h in day_hours.values())

        gross = round(regular_hours * hourly_rate + overtime_hours * hourly_rate * self.overtime_multiplier, 2)
        adjustments = round(self._sum_adjustments(employee_id, year, month), 2)
        # apply adjustments (allowances positive, deductions negative)
        net_before_tax = gross + adjustments
        tax = round(net_before_tax * self.tax_policy.rate, 2)
        net = round(net_before_tax - tax, 2)

        return {
            "employee_id": employee_id,
            "full_name": full_name,
            "period": f"{year:04d}-{month:02d}",
            "hourly_rate": round(hourly_rate, 2),
            "regular_hours": round(regular_hours, 2),
            "overtime_hours": round(overtime_hours, 2),
            "gross": gross,
            "adjustments": adjustments,
            "tax": tax,
            "net": net
        }

    def persist_for_employee(self, employee_id: int, year: int, month: int, hourly_rate: Optional[float] = None) -> dict:
        """
        Compute payroll for a single employee for year/month and insert or update payroll_runs.
        Returns the computed payroll dict.
        """
        pr = self.compute_for_employee(employee_id, year, month, hourly_rate=hourly_rate)

        exists = self.db.fetchone("SELECT id FROM payroll_runs WHERE employee_id = ? AND year = ? AND month = ?", (employee_id, year, month))
        if exists:
            self.db.execute("""UPDATE payroll_runs SET
                                regular_hours = ?, overtime_hours = ?, hourly_rate = ?, gross_pay = ?, total_adjustments = ?, net_pay = ?
                                WHERE id = ?""",
                            (pr.get("regular_hours"), pr.get("overtime_hours"), pr.get("hourly_rate"), pr.get("gross"), pr.get("adjustments", 0.0), pr.get("net"), exists["id"]))
        else:
            self.db.execute("""INSERT INTO payroll_runs
                               (employee_id, year, month, regular_hours, overtime_hours, hourly_rate, gross_pay, total_adjustments, net_pay)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (employee_id, year, month, pr.get("regular_hours"), pr.get("overtime_hours"), pr.get("hourly_rate"), pr.get("gross"), pr.get("adjustments", 0.0), pr.get("net")))
        return pr

    def generate_payroll_for_month(self, year: int, month: int) -> List[dict]:
        """
        Compute payroll for all active employees and persist into payroll_runs.
        Returns list of dict rows computed.
        """
        rows = self.db.query("SELECT id, full_name, role, department, contact, rate FROM employees WHERE active = 1")
        results = []
        for emp in rows:
            emp_id = emp["id"]
            full_name = emp["full_name"]
            rate = float(emp["rate"])
            try:
                pr = self.compute_for_employee(emp_id, year, month, hourly_rate=rate)
                # persist into payroll_runs table
                self.db.execute("""INSERT INTO payroll_runs
                                   (employee_id, year, month, regular_hours, overtime_hours, hourly_rate, gross_pay, total_adjustments, net_pay)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (emp_id, year, month, pr["regular_hours"], pr["overtime_hours"], pr["hourly_rate"], pr["gross"], pr.get("adjustments", 0.0), pr["net"]))
                results.append(pr)
            except Exception as e:
                print(f"Error computing payroll for employee {emp_id}: {e}")
        return results

    def export_monthly_csv(self, year: int, month: int, out_path: Optional[str] = None) -> str:
        """Export payroll for a month to CSV."""
        results = self.generate_payroll_for_month(year, month)
        if not results:
            raise ValueError(f"No payroll data for {year}-{month:02d}")
        
        out_path = out_path or f"payroll_{year}_{month:02d}.csv"
        
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "employee_id", "full_name", "period", "hourly_rate", 
                "regular_hours", "overtime_hours", "gross", "adjustments", "tax", "net"
            ])
            writer.writeheader()
            writer.writerows(results)
        
        return str(out_path)

    def export_individual_payslip_csv(self, employee_id: int, year: int, month: int, out_path: Optional[str] = None) -> str:
        """Export individual payslip to CSV."""
        pr = self.compute_for_employee(employee_id, year, month)
        emp = self.db.fetchone("SELECT id, full_name, role, department, contact, rate FROM employees WHERE id = ?", (employee_id,))
        full_name = emp["full_name"] if emp else f"Employee {employee_id}"
        out_path = out_path or f"payslip_{employee_id}_{year}_{month:02d}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Payslip", full_name])
            writer.writerow(["Employee ID", employee_id])
            writer.writerow(["Period", f"{year:04d}-{month:02d}"])
            writer.writerow([])
            writer.writerow(["Hourly Rate", pr.get("hourly_rate", "N/A")])
            writer.writerow(["Regular Hours", pr.get("regular_hours")])
            writer.writerow(["Overtime Hours", pr.get("overtime_hours")])
            writer.writerow(["Gross", pr.get("gross")])
            writer.writerow(["Adjustments", pr.get("adjustments", 0.0)])
            writer.writerow(["Tax", pr.get("tax")])
            writer.writerow(["Net", pr.get("net")])
        return out_path

    def export_individual_payslip_pdf(self, employee_id: int, year: int, month: int, out_path: Optional[str] = None) -> str:
        """Export individual payslip to PDF (fallback to CSV if reportlab missing)."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except Exception:
            return self.export_individual_payslip_csv(employee_id, year, month, out_path=f"{out_path or 'payslip'}.csv")

        pr = self.compute_for_employee(employee_id, year, month)
        emp = self.db.fetchone("SELECT id, full_name FROM employees WHERE id = ?", (employee_id,))
        full_name = emp["full_name"] if emp else f"Employee {employee_id}"
        out_path = out_path or f"payslip_{employee_id}_{year}_{month:02d}.pdf"

        c = canvas.Canvas(out_path, pagesize=A4)
        text = c.beginText(40, 800)
        text.setFont("Helvetica-Bold", 14)
        text.textLine(f"Payslip - {year:04d}-{month:02d}")
        text.setFont("Helvetica", 10)
        text.textLine(f"Employee: {full_name} (ID: {employee_id})")
        text.textLine(" ")
        text.textLine(f"Hourly Rate: {pr.get('hourly_rate', 'N/A')}")
        text.textLine(f"Regular Hours: {pr.get('regular_hours')}")
        text.textLine(f"Overtime Hours: {pr.get('overtime_hours')}")
        text.textLine(f"Gross: {pr.get('gross')}")
        text.textLine(f"Adjustments: {pr.get('adjustments', 0.0)}")
        text.textLine(f"Tax: {pr.get('tax')}")
        text.textLine(f"Net: {pr.get('net')}")
        c.drawText(text)
        c.showPage()
        c.save()
        return out_path