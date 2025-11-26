from tabulate import tabulate
from typing import Any, Iterable
import shutil

class CLIView:
    def display_message(self, message: str):
        """Display a general message."""
        print(f"\n{message}\n")

    def display_error(self, message: str):
        """Display an error message."""
        print(f"\n❌ ERROR: {message}\n")

    def display_success(self, message: str):
        """Display a success message."""
        print(f"\n✅ {message}\n")

    def display_exit_message(self):
        """Display exit message."""
        print("\nGoodbye!\n")

    def display_welcome_message(self, username: str = "User"):
        """Display welcome message."""
        print("\n" + "="*50)
        print(f"Welcome to QuickHire - Signed in as: {username}")
        print("="*50 + "\n")

    def display_invalid_choice_message(self):
        """Display invalid choice message."""
        print("\n⚠️  Invalid choice. Please try again.\n")

    def prompt_for_input(self, prompt: str) -> str:
        """Get user input."""
        return input(prompt)

    def get_user_choice(self, is_admin: bool = False) -> str:
        """Display main menu and get user choice."""
        print("\n" + "-"*50)
        print("Main Menu")
        print("-"*50)
        print("1. Attendance (Sign In/Out)")
        if is_admin:
            print("2. Manage Employees (Admin)")
            print("3. Payroll (Admin)")
            print("4. Reports (Admin)")
        print("Q. Quit")
        print("-"*50)
        return self.prompt_for_input("Choose an option: ").strip()

    def display_attendance_menu(self):
        """Display attendance submenu."""
        print("\n" + "-"*50)
        print("Attendance Menu")
        print("-"*50)
        print("1. Sign In")
        print("2. Sign Out")
        print("3. Add Correction (Admin)")
        print("4. View Records")
        print("5. Delete Record (Admin)")
        print("6. Back")
        print("-"*50)

    def display_employees_menu(self):
        """Display employees submenu."""
        print("\n" + "-"*50)
        print("Employees Menu")
        print("-"*50)
        print("1. Add Employee")
        print("2. List Employees")
        print("3. View Employee")
        print("4. Edit Employee")
        print("5. Delete Employee")
        print("6. Back")
        print("-"*50)

    def display_payroll_menu(self):
        """Display payroll submenu."""
        print("\n" + "-"*50)
        print("Payroll Menu")
        print("-"*50)
        print("1. Generate Payroll for Month")
        print("2. View Payroll")
        print("3. Export to CSV")
        print("4. Back")
        print("-"*50)

    def display_reports_menu(self):
        """Display reports submenu."""
        print("\n" + "-"*50)
        print("Reports Menu")
        print("-"*50)
        print("1. Attendance Report")
        print("2. Payroll Report")
        print("3. Back")
        print("-"*50)

    # --- Helpers to normalize row-like objects to dict ---
    def _to_mapping(self, row):
        """
        Normalize sqlite3.Row or other mapping-like objects to a plain dict.
        If row is already a dict, return it.
        """
        if row is None:
            return {}
        if isinstance(row, dict):
            return row
        # sqlite3.Row and similar have .keys()
        if hasattr(row, "keys"):
            try:
                return {k: row[k] for k in row.keys()}
            except Exception:
                pass
        # Fallback: try attribute access
        try:
            return row.__dict__
        except Exception:
            return {}

    def _cell(self, row, col):
        """Robustly get a column value from row (sqlite3.Row, dict, or object)."""
        try:
            return row[col]
        except Exception:
            pass
        if isinstance(row, dict):
            return row.get(col, "")
        try:
            return getattr(row, col, "")
        except Exception:
            return ""

    # --- Data display helpers ---
    def display_employee(self, row):
        """Display a single employee record in key-value format."""
        if not row:
            print("\nEmployee not found\n")
            return
        cols = ["id", "full_name", "role", "department", "contact", "rate", "active"]
        print("\n" + "="*60)
        for c in cols:
            val = self._cell(row, c)
            print(f"  {c.upper():<15}: {val}")
        print("="*60 + "\n")

    def display_employees_list(self, rows):
        """Display employees in a formatted table."""
        if not rows:
            print("\nNo employees found\n")
            return
        
        cols = ["id", "full_name", "role", "department", "contact", "rate", "active"]
        widths = {c: len(c) for c in cols}
        
        # Calculate column widths
        for r in rows:
            for c in cols:
                val = str(self._cell(r, c) or "")
                widths[c] = max(widths[c], len(val))
        
        # Print header
        header = " | ".join(c.upper().ljust(widths[c]) for c in cols)
        sep = "-+-".join("-" * widths[c] for c in cols)
        print("\n" + header)
        print(sep)
        
        # Print rows
        for r in rows:
            line = " | ".join(str(self._cell(r, c) or "").ljust(widths[c]) for c in cols)
            print(line)
        print()

    def display_employees(self, rows):
        """Alias for display_employees_list for compatibility."""
        self.display_employees_list(rows)

    def display_attendance_records(self, records):
        """Display attendance records with employee name."""
        if not records:
            print("\nNo records found\n")
            return
        
        cols = ["id", "employee_id", "full_name", "event", "timestamp", "corrected_by_hr", "note"]
        widths = {c: len(c) for c in cols}
        
        for r in records:
            for c in cols:
                val = str(self._cell(r, c) or "")
                widths[c] = max(widths[c], len(val))
        
        header = " | ".join(c.upper().ljust(widths[c]) for c in cols)
        sep = "-+-".join("-" * widths[c] for c in cols)
        print("\n" + header)
        print(sep)
        
        for r in records:
            line = " | ".join(str(self._cell(r, c) or "").ljust(widths[c]) for c in cols)
            print(line)
        print()
