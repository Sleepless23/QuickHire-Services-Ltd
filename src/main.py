import pathlib
import sys
from getpass import getpass

# Ensure src/ (this folder) is on sys.path so "controllers", "models", "services", "views" resolve.
SRC_DIR = pathlib.Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from views.cli_view import CLIView
from models.database import Database
from models.user import UserModel
from controllers.employees_controller import EmployeesController
from controllers.attendance_controller import AttendanceController
from controllers.payroll_controller import PayrollController
from controllers.reports_controller import ReportsController
from services.payroll_service import PayrollService

def bootstrap():
    view = CLIView()
    db = Database()  # ensures schema exists
    user_model = UserModel(db)

    view.display_message("Please sign in")
    username = view.prompt_for_input("Username: ").strip()
    # use getpass so password not echoed
    password = getpass("Password: ")
    user = user_model.authenticate(username, password)
    if not user:
        view.display_error("Authentication failed. Exiting.")
        return None

    # prepare service/controllers with current_user context
    payroll_service = PayrollService(db)
    employees_ctrl = EmployeesController(db=db, view=view, current_user=user)
    attendance_ctrl = AttendanceController(db=db, view=view, current_user=user, payroll_service=payroll_service)
    payroll_ctrl = PayrollController(db=db, view=view, payroll_service=payroll_service, current_user=user)
    reports_ctrl = ReportsController(db=db, view=view, payroll_service=payroll_service, attendance_controller=attendance_ctrl, current_user=user)

    return {
        "view": view,
        "db": db,
        "user": user,
        "employees_ctrl": employees_ctrl,
        "attendance_ctrl": attendance_ctrl,
        "payroll_ctrl": payroll_ctrl,
        "reports_ctrl": reports_ctrl
    }

def main():
    ctx = bootstrap()
    if ctx is None:
        return

    view = ctx["view"]
    employees = ctx["employees_ctrl"]
    attendance = ctx["attendance_ctrl"]
    payroll = ctx["payroll_ctrl"]
    reports = ctx["reports_ctrl"]
    current_user = ctx["user"]

    view.display_welcome_message(current_user.username)
    while True:
        choice = view.get_user_choice(current_user.is_hr)
        if choice == "1":
            attendance.handle_attendance()
        elif choice == "2":
            # Only admins can access employees
            if getattr(current_user, "is_hr", False):
                employees.handle_employees()
            else:
                view.display_error("Only admins can manage employees")
        elif choice == "3":
            # Only admins can access payroll
            if getattr(current_user, "is_hr", False):
                payroll.handle_payroll()
            else:
                view.display_error("Only admins can access payroll")
        elif choice == "4":
            # Only admins can access reports
            if getattr(current_user, "is_hr", False):
                reports.handle_reports()
            else:
                view.display_error("Only admins can access reports")
        elif choice.lower() == "q":
            view.display_exit_message()
            break
        else:
            view.display_invalid_choice_message()

if __name__ == "__main__":
    main()
