from functools import wraps
import os
import hashlib
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

import mysql.connector
from dotenv import load_dotenv

load_dotenv()
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from mysql.connector import Error, IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
# Configure these values in your environment or .env file. Never commit real secrets.
app.secret_key = os.getenv("SECRET_KEY", "7d4be823d72ef1ee8e84888b64719f6c8f12dbb7ddfb0b00e8af74c66d98d968")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
DB_NAME = os.getenv("DB_NAME", "company")
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "nagarjunabande8@gmail.com")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "icsm fzrt zbrb tliz")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "300"))

def send_reset_email(recipient, reset_url):
    """Send a password reset link using configured SMTP credentials."""
    if not MAIL_USERNAME or not MAIL_PASSWORD or not MAIL_FROM:
        raise RuntimeError("Email is not configured. Set MAIL_USERNAME, MAIL_PASSWORD, and MAIL_FROM in .env.")
    message = EmailMessage()
    message["Subject"] = "Reset your Employee Management System password"
    message["From"] = MAIL_FROM
    message["To"] = recipient
    message.set_content(
        "We received a request to reset your password. Open this one-time link within "
        f"{RESET_TOKEN_MINUTES} minutes:\n\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    context = ssl.create_default_context()
    with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=20) as server:
        server.starttls(context=context)
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(message)

def get_server_connection():
    """Return a MySQL connection without selecting a database."""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def get_db():
    """Return a MySQL connection to the application database."""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )

def init_db():
    """Create the database and required tables if they do not exist."""
    connection = None
    cursor = None

    try:
        connection = get_server_connection()
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

    connection = None
    cursor = None

    try:
        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(254) NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'admin',
                reset_token_hash CHAR(64) NULL,
                reset_expires_at DATETIME NULL
            )
            """
        )

        # Add password-reset columns to databases created by older versions.
        cursor.execute("SHOW COLUMNS FROM users")
        existing_columns = {row[0] for row in cursor.fetchall()}
        if "email" not in existing_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(254) NULL")
        if "reset_token_hash" not in existing_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN reset_token_hash CHAR(64) NULL")
        if "reset_expires_at" not in existing_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN reset_expires_at DATETIME NULL")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS employee (
                eid INT PRIMARY KEY,
                ename VARCHAR(50) NOT NULL,
                edept VARCHAR(50) NOT NULL,
                esalary INT NOT NULL,
                ephone VARCHAR(15) NOT NULL
            )
            """
        )

        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("Unauthorized access.", "danger")
            return redirect(url_for("home"))

        return view_function(*args, **kwargs)

    return wrapped_view


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not subject or not message:
            flash("Please complete all contact form fields.", "danger")
            return render_template("contact.html")

        flash("Thank you for contacting us.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username:
            flash("Username is required.", "danger")
            return render_template("register.html")

        if not password:
            flash("Password is required.", "danger")
            return render_template("register.html")

        if not confirm_password:
            flash("Please confirm your password.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if len(username) > 50:
            flash("Username must be 50 characters or fewer.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return render_template("register.html")

        connection = None
        cursor = None

        try:
            connection = get_db()
            cursor = connection.cursor()

            cursor.execute(
                "SELECT id FROM users WHERE username = %s",
                (username,),
            )
            if cursor.fetchone():
                flash("Username already exists.", "danger")
                return render_template("register.html")

            hashed_password = generate_password_hash(password)

            cursor.execute(
                """
                INSERT INTO users (username, email, password, role)
                VALUES (%s, %s, %s, %s)
                """,
                (username, email or None, hashed_password, "admin"),
            )
            connection.commit()

            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except IntegrityError:
            if connection is not None:
                connection.rollback()
            flash("Username already exists.", "danger")
            return render_template("register.html")
        except Error:
            if connection is not None:
                connection.rollback()
            flash("Unable to complete registration. Please try again.", "danger")
            return render_template("register.html")
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html")

        connection = None
        cursor = None

        try:
            connection = get_db()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT username, password, role
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            user = cursor.fetchone()

            if user and check_password_hash(user["password"], password):
                session["username"] = user["username"]
                session["logged_in"] = True
                session["role"] = user["role"]

                flash("Login successful.", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        except Error:
            flash("Unable to process login. Please try again.", "danger")
            return render_template("login.html")
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your registered email address.", "danger")
            return render_template("forgot_password.html")

        connection = None
        cursor = None
        try:
            connection = get_db()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, email FROM users WHERE LOWER(email) = %s", (email,))
            user = cursor.fetchone()
            # Keep the response generic so the page does not reveal registered accounts.
            if user and user.get("email"):
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_MINUTES)
                cursor.execute(
                    "UPDATE users SET reset_token_hash=%s, reset_expires_at=%s WHERE id=%s",
                    (token_hash, expires_at, user["id"]),
                )
                connection.commit()
                reset_url = url_for("reset_password", token=token, _external=True)
                try:
                    send_reset_email(user["email"], reset_url)
                except Exception:
                    app.logger.exception("Password reset email could not be sent")
                    flash("Email could not be sent. Check SMTP settings in your .env file and try again.", "danger")
                    return render_template("forgot_password.html")
            flash("If that email is registered, a password reset link has been sent.", "info")
            return redirect(url_for("login"))
        except Error:
            app.logger.exception("Password reset request failed")
            flash("Unable to process your request right now. Please try again.", "danger")
            return render_template("forgot_password.html")
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()
    return render_template("forgot_password.html")



@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    connection = None
    cursor = None

    try:
        connection = get_db()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE reset_token_hash = %s
              AND reset_expires_at > UTC_TIMESTAMP()
            """,
            (token_hash,)
        )

        user = cursor.fetchone()

        if not user:
            flash(
                "This reset link is invalid or has expired. "
                "Please request a new one.",
                "warning"
            )
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm_password = request.form.get(
                "confirm_password", ""
            )

            if len(password) < 8:
                flash(
                    "Password must contain at least 8 characters.",
                    "danger"
                )

            elif password != confirm_password:
                flash("Passwords do not match.", "danger")

            else:
                cursor.execute(
                    """
                    UPDATE users
                    SET password = %s,
                        reset_token_hash = NULL,
                        reset_expires_at = NULL
                    WHERE id = %s
                    """,
                    (
                        generate_password_hash(password),
                        user["id"]
                    )
                )

                connection.commit()

                flash(
                    "Password updated successfully. "
                    "You can now log in with your new password.",
                    "success"
                )

                return redirect(url_for("login"))

        return render_template("reset_password.html")

    except Error:
        if connection is not None:
            connection.rollback()

        app.logger.exception("Password reset failed")

        flash(
            "Unable to reset the password right now. "
            "Please try again.",
            "danger"
        )

        return redirect(url_for("forgot_password"))

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()



@app.route("/dashboard")
@admin_required
def dashboard():
    connection = None
    cursor = None
    total_employees = 0
    total_departments = 0

    try:
        connection = get_db()
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM employee")
        total_employees = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT edept) FROM employee")
        total_departments = cursor.fetchone()[0]

    except Error:
        flash("Unable to load dashboard statistics.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

    return render_template(
        "dashboard.html",
        total_employees=total_employees,
        total_departments=total_departments,
    )


@app.route("/add-employee", methods=["GET", "POST"])
@admin_required
def add_employee():
    if request.method == "POST":
        eid_value = request.form.get("eid", "").strip()
        ename = request.form.get("ename", "").strip()
        edept = request.form.get("edept", "").strip()
        esalary_value = request.form.get("esalary", "").strip()
        ephone = request.form.get("ephone", "").strip()

        if not eid_value or not ename or not edept or not esalary_value or not ephone:
            flash("All employee fields are required.", "danger")
            return render_template("add_employee.html")

        try:
            eid = int(eid_value)
            esalary = int(esalary_value)
        except ValueError:
            flash("Employee ID and salary must be valid numbers.", "danger")
            return render_template("add_employee.html")

        if eid <= 0:
            flash("Employee ID must be greater than zero.", "danger")
            return render_template("add_employee.html")

        if esalary < 0:
            flash("Salary cannot be negative.", "danger")
            return render_template("add_employee.html")

        if len(ename) > 50 or len(edept) > 50 or len(ephone) > 15:
            flash("One or more fields exceed the allowed length.", "danger")
            return render_template("add_employee.html")

        connection = None
        cursor = None

        try:
            connection = get_db()
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO employee (eid, ename, edept, esalary, ephone)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (eid, ename, edept, esalary, ephone),
            )
            connection.commit()

            flash("Employee added successfully.", "success")
            return redirect(url_for("view_employees"))

        except IntegrityError:
            if connection is not None:
                connection.rollback()
            flash("Employee ID already exists.", "danger")
            return render_template("add_employee.html")
        except Error:
            if connection is not None:
                connection.rollback()
            flash("Unable to add employee. Please try again.", "danger")
            return render_template("add_employee.html")
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("add_employee.html")


@app.route("/view-employees")
@admin_required
def view_employees():
    search = request.args.get("search", "").strip()
    employees = []

    connection = None
    cursor = None

    try:
        connection = get_db()
        cursor = connection.cursor()

        if search:
            search_pattern = f"%{search}%"
            cursor.execute(
                """
                SELECT eid, ename, edept, esalary, ephone
                FROM employee
                WHERE CAST(eid AS CHAR) LIKE %s
                   OR ename LIKE %s
                   OR edept LIKE %s
                   OR ephone LIKE %s
                ORDER BY eid
                """,
                (
                    search_pattern,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                ),
            )
        else:
            cursor.execute(
                """
                SELECT eid, ename, edept, esalary, ephone
                FROM employee
                ORDER BY eid
                """
            )

        employees = cursor.fetchall()

    except Error:
        flash("Unable to load employee records.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

    return render_template(
        "view_employees.html",
        employees=employees,
        search=search,
    )


@app.route("/edit/<int:eid>", methods=["GET", "POST"])
@admin_required
def edit_employee(eid):
    connection = None
    cursor = None
    employee = None

    try:
        connection = get_db()
        cursor = connection.cursor()

        if request.method == "GET":
            cursor.execute(
                """
                SELECT eid, ename, edept, esalary, ephone
                FROM employee
                WHERE eid = %s
                """,
                (eid,),
            )
            employee = cursor.fetchone()

            if employee is None:
                flash("Employee not found.", "warning")
                return redirect(url_for("view_employees"))

            return render_template(
                "edit_employee.html",
                employee=employee,
            )

        ename = request.form.get("ename", "").strip()
        edept = request.form.get("edept", "").strip()
        esalary_value = request.form.get("esalary", "").strip()
        ephone = request.form.get("ephone", "").strip()

        if not ename or not edept or not esalary_value or not ephone:
            flash("All employee fields are required.", "danger")
            employee = (eid, ename, edept, esalary_value, ephone)
            return render_template(
                "edit_employee.html",
                employee=employee,
            )

        try:
            esalary = int(esalary_value)
        except ValueError:
            flash("Salary must be a valid number.", "danger")
            employee = (eid, ename, edept, esalary_value, ephone)
            return render_template(
                "edit_employee.html",
                employee=employee,
            )

        if esalary < 0:
            flash("Salary cannot be negative.", "danger")
            employee = (eid, ename, edept, esalary_value, ephone)
            return render_template(
                "edit_employee.html",
                employee=employee,
            )

        if len(ename) > 50 or len(edept) > 50 or len(ephone) > 15:
            flash("One or more fields exceed the allowed length.", "danger")
            employee = (eid, ename, edept, esalary, ephone)
            return render_template(
                "edit_employee.html",
                employee=employee,
            )

        cursor.execute(
            """
            UPDATE employee
            SET ename = %s,
                edept = %s,
                esalary = %s,
                ephone = %s
            WHERE eid = %s
            """,
            (ename, edept, esalary, ephone, eid),
        )
        connection.commit()

        if cursor.rowcount == 0:
            flash("Employee not found.", "warning")
        else:
            flash("Employee updated successfully.", "success")

        return redirect(url_for("view_employees"))

    except Error:
        if connection is not None:
            connection.rollback()
        flash("Unable to update employee. Please try again.", "danger")
        return redirect(url_for("view_employees"))
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/delete/<int:eid>", methods=["POST"])
@admin_required
def delete_employee(eid):
    connection = None
    cursor = None

    try:
        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM employee WHERE eid = %s",
            (eid,),
        )
        connection.commit()

        if cursor.rowcount:
            flash("Employee deleted successfully.", "success")
        else:
            flash("Employee not found.", "warning")

    except Error:
        if connection is not None:
            connection.rollback()
        flash("Unable to delete employee. Please try again.", "danger")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

    return redirect(url_for("view_employees"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(error):
    return render_template("500.html"), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
