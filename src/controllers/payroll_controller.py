import sqlite3
from datetime import datetime
from typing import Any

class PayrollController:
    def __init__(self, db, view, payroll_service=None, current_user=None):
        self.db = db
        self.view = view
        self.payroll_service = payroll_service
        self.current_user = current_user

    def _check_admin(self):
        """Raise error if not admin."""
        if not getattr(self.current_user, "is_hr", False):
            raise PermissionError("Only admins can access payroll")

    def _format_pr(self, pr: Any) -> str:
        """Format payroll dict or dataclass for display."""
        if pr is None:
            return "No payroll data"
        if isinstance(pr, dict):
            hourly_rate = pr.get('hourly_rate', 0)
            try:
                hourly_rate = float(hourly_rate)
            except (ValueError, TypeError):
                hourly_rate = 0
            lines = [
                f"Employee ID     : {pr.get('employee_id')}",
                f"Full Name       : {pr.get('full_name')}",
                f"Period          : {pr.get('period')}",
                f"Hourly Rate     : ${hourly_rate:.2f}",
                f"Regular Hours   : {pr.get('regular_hours')}",
                f"Overtime Hours  : {pr.get('overtime_hours')}",
                f"Gross Pay       : ${pr.get('gross', 0):.2f}",
                f"Adjustments     : ${pr.get('adjustments', 0):.2f}",
                f"Tax (15%)       : ${pr.get('tax', 0):.2f}",
                f"Net Pay         : ${pr.get('net', 0):.2f}",
            ]
            return "\n".join(lines)
        # dataclass-like
        parts = []
        for k in ("employee_id", "period", "hourly_rate", "regular_hours", "overtime_hours", "gross", "tax", "net"):
            val = getattr(pr, k, None)
            parts.append(f"{k}: {val}")
        return "\n".join(parts)

    def handle_payroll(self):
        view = self.view
        if view is None:
            print("No view configured")
            return

        try:
            self._check_admin()
        except PermissionError as e:
            view.display_error(str(e))
            return

        while True:
            view.display_payroll_menu()
            ch = view.prompt_for_input("Choose (number): ").strip()
            if ch == "1":  # Generate payroll for month (persist)
                try:
                    year_s = view.prompt_for_input("Year (YYYY): ").strip()
                    month_s = view.prompt_for_input("Month (1-12): ").strip()
                    year = int(year_s)
                    month = int(month_s)
                    if not (1 <= month <= 12):
                        view.display_error("Month must be 1-12")
                        continue
                    confirm = view.prompt_for_input(f"Generate and persist payroll for {year}-{month:02d}? (y/n): ").strip().lower()
                    if confirm != "y":
                        view.display_message("Cancelled")
                        continue
                    # generate (persist) -- catch DB errors and show friendly message
                    try:
                        results = self.payroll_service.generate_payroll_for_month(year, month)
                    except sqlite3.IntegrityError as ie:
                        # possible duplicate insert constraints; show message and continue
                        view.display_error(f"Database integrity error while generating payroll: {ie}")
                        continue
                    except Exception as e:
                        view.display_error(f"Error generating payroll: {e}")
                        continue

                    count = len(results) if isinstance(results, (list, tuple)) else 0
                    view.display_success(f"Payroll generated for {year}-{month:02d} ({count} employees).")
                except ValueError:
                    view.display_error("Invalid year/month input")
                except Exception as e:
                    view.display_error(f"Unexpected error: {e}")

            elif ch == "2":  # View payroll for employee (compute, do not persist)
                try:
                    eid_s = view.prompt_for_input("Employee ID: ").strip()
                    year_s = view.prompt_for_input("Year (YYYY): ").strip()
                    month_s = view.prompt_for_input("Month (1-12): ").strip()
                    if not eid_s or not year_s or not month_s:
                        view.display_error("Employee ID, Year and Month are required")
                        continue
                    eid = int(eid_s)
                    year = int(year_s)
                    month = int(month_s)
                    pr = self.payroll_service.compute_for_employee(eid, year, month)
                    view.display_message(self._format_pr(pr))
                except ValueError:
                    view.display_error("Invalid numeric input")
                except Exception as e:
                    view.display_error(f"Error computing payroll: {e}")

            elif ch == "3":  # Export CSV
                try:
                    year_s = view.prompt_for_input("Year (YYYY): ").strip()
                    month_s = view.prompt_for_input("Month (1-12): ").strip()
                    if not year_s or not month_s:
                        view.display_error("Year and Month required")
                        continue
                    year = int(year_s)
                    month = int(month_s)
                    # export_monthly_csv should compute and write CSV; catch errors
                    try:
                        path = self.payroll_service.export_monthly_csv(year, month)
                        view.display_success(f"Exported payroll CSV to: {path}")
                    except Exception as e:
                        view.display_error(f"Export failed: {e}")
                except ValueError:
                    view.display_error("Invalid year/month")
                except Exception as e:
                    view.display_error(f"Unexpected error: {e}")

            elif ch == "4":  # Back
                break

            else:
                view.display_invalid_choice_message()
