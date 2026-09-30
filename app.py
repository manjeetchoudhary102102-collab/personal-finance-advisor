import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, redirect, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "dev-secret-change-me"
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{INSTANCE_DIR / 'finance.db'}"
).replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ============================================================
# FLASK LOGIN
# ============================================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.unauthorized_handler
def unauthorized():
    """
    API requests receive JSON instead of an HTML redirect.
    Normal browser requests go to the login page.
    """
    if request.path.startswith("/api/"):
        return jsonify({
            "ok": False,
            "error": "Authentication required."
        }), 401

    next_url = request.full_path
    return redirect(url_for("login", next=next_url))


# ============================================================
# CONSTANTS
# ============================================================

CATEGORIES = [
    "Food",
    "Rent",
    "Transport",
    "Entertainment",
    "Shopping",
    "Education",
    "Healthcare",
    "Utilities",
    "Other",
]

BUDGET_RULES = {
    "Rent": 30,
    "Food": 12,
    "Transport": 8,
    "Utilities": 8,
    "Healthcare": 5,
    "Education": 7,
    "Entertainment": 5,
    "Shopping": 5,
    "Other": 5,
}


# ============================================================
# MODELS
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(120),
        nullable=False
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="user"
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    incomes = db.relationship(
        "Income",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    expenses = db.relationship(
        "Expense",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Income(db.Model):
    __tablename__ = "income"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    month = db.Column(
        db.String(7),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "month",
            name="uq_income_user_month"
        ),
    )


class Expense(db.Model):
    __tablename__ = "expense"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False
    )

    category = db.Column(
        db.String(40),
        nullable=False
    )

    description = db.Column(
        db.String(255),
        nullable=False
    )

    date = db.Column(
        db.Date,
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )


# ============================================================
# FLASK-LOGIN USER LOADER
# ============================================================

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# ============================================================
# DATABASE MIGRATION
# ============================================================

def migrate_database():
    """
    Safely updates the existing empty PostgreSQL finance tables.

    The old database has already been cleared, so user_id can be
    made NOT NULL without losing existing finance records.
    """

    dialect = db.engine.dialect.name

    if dialect != "postgresql":
        return

    inspector_sql = text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('income', 'expense')
    """)

    existing_tables = {
        row[0]
        for row in db.session.execute(inspector_sql).fetchall()
    }

    # --------------------------------------------------------
    # Income migration
    # --------------------------------------------------------

    if "income" in existing_tables:

        income_user_id = db.session.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'income'
              AND column_name = 'user_id'
        """)).first()

        if not income_user_id:
            db.session.execute(text("""
                ALTER TABLE income
                ADD COLUMN user_id INTEGER
            """))

        # The old unique month index prevents different users
        # from having income for the same month.
        db.session.execute(text("""
            DROP INDEX IF EXISTS ix_income_month
        """))

        # Existing records were already deleted before this migration.
        db.session.execute(text("""
            ALTER TABLE income
            ALTER COLUMN user_id SET NOT NULL
        """))

        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_income_user_id
            ON income (user_id)
        """))

        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_income_user_month
            ON income (user_id, month)
        """))

        # Add foreign key if it does not already exist.
        fk_exists = db.session.execute(text("""
            SELECT 1
            FROM information_schema.table_constraints
            WHERE constraint_schema = 'public'
              AND table_name = 'income'
              AND constraint_name = 'fk_income_user'
        """)).first()

        if not fk_exists:
            db.session.execute(text("""
                ALTER TABLE income
                ADD CONSTRAINT fk_income_user
                FOREIGN KEY (user_id)
                REFERENCES "user"(id)
                ON DELETE CASCADE
            """))

    # --------------------------------------------------------
    # Expense migration
    # --------------------------------------------------------

    if "expense" in existing_tables:

        expense_user_id = db.session.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'expense'
              AND column_name = 'user_id'
        """)).first()

        if not expense_user_id:
            db.session.execute(text("""
                ALTER TABLE expense
                ADD COLUMN user_id INTEGER
            """))

        db.session.execute(text("""
            ALTER TABLE expense
            ALTER COLUMN user_id SET NOT NULL
        """))

        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_expense_user_id
            ON expense (user_id)
        """))

        fk_exists = db.session.execute(text("""
            SELECT 1
            FROM information_schema.table_constraints
            WHERE constraint_schema = 'public'
              AND table_name = 'expense'
              AND constraint_name = 'fk_expense_user'
        """)).first()

        if not fk_exists:
            db.session.execute(text("""
                ALTER TABLE expense
                ADD CONSTRAINT fk_expense_user
                FOREIGN KEY (user_id)
                REFERENCES "user"(id)
                ON DELETE CASCADE
            """))

    db.session.commit()


# ============================================================
# VALIDATION HELPERS
# ============================================================

def parse_amount(value):
    try:
        amount = Decimal(str(value)).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if amount > Decimal("999999999.99"):
        raise ValueError("Amount is too large.")

    return amount


def parse_date(value):
    try:
        return datetime.strptime(
            str(value),
            "%Y-%m-%d"
        ).date()
    except (TypeError, ValueError):
        raise ValueError(
            "Date must use YYYY-MM-DD format."
        )


def normalize_email(value):
    email = str(value or "").strip().lower()

    if not email:
        raise ValueError("Email is required.")

    if len(email) > 255:
        raise ValueError("Email is too long.")

    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Please enter a valid email address.")

    return email


def validate_password(password):
    password = str(password or "")

    if len(password) < 8:
        raise ValueError(
            "Password must contain at least 8 characters."
        )

    if len(password) > 128:
        raise ValueError(
            "Password is too long."
        )

    return password


def validate_name(name):
    name = str(name or "").strip()

    if not name:
        raise ValueError("Name is required.")

    if len(name) > 120:
        raise ValueError("Name is too long.")

    return name


def current_month():
    return date.today().strftime("%Y-%m")


def get_month_from_request():
    month = (
        request.args.get("month")
        or request.form.get("month")
        or current_month()
    )

    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise ValueError(
            "Month must use YYYY-MM format."
        )

    return month


# ============================================================
# USER-SPECIFIC DATA HELPERS
# ============================================================

def month_expenses(month):
    start = datetime.strptime(
        month + "-01",
        "%Y-%m-%d"
    ).date()

    if start.month == 12:
        end = date(
            start.year + 1,
            1,
            1
        )
    else:
        end = date(
            start.year,
            start.month + 1,
            1
        )

    return Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= start,
        Expense.date < end
    )


def money(value):
    return float(
        Decimal(value or 0).quantize(
            Decimal("0.01")
        )
    )


def expense_to_dict(expense):
    return {
        "id": expense.id,
        "amount": money(expense.amount),
        "category": expense.category,
        "description": expense.description,
        "date": expense.date.isoformat(),
    }


# ============================================================
# DASHBOARD
# ============================================================

def build_summary(month):
    income_row = Income.query.filter_by(
        month=month,
        user_id=current_user.id
    ).first()

    income = money(
        income_row.amount
        if income_row
        else 0
    )

    expenses = month_expenses(month).all()

    total_expenses = money(
        sum(
            (
                Decimal(str(e.amount))
                for e in expenses
            ),
            Decimal("0")
        )
    )

    savings = round(
        income - total_expenses,
        2
    )

    savings_percentage = round(
        (savings / income) * 100,
        1
    ) if income else 0

    category_totals = {
        category: 0.0
        for category in CATEGORIES
    }

    for expense in expenses:
        category_totals[
            expense.category
        ] = round(
            category_totals.get(
                expense.category,
                0
            ) + money(expense.amount),
            2
        )

    nonzero = {
        key: value
        for key, value in category_totals.items()
        if value > 0
    }

    highest_category = (
        max(
            nonzero,
            key=nonzero.get
        )
        if nonzero
        else None
    )

    recent = sorted(
        expenses,
        key=lambda x: (
            x.date,
            x.id
        ),
        reverse=True
    )[:5]

    return {
        "month": month,
        "income": income,
        "total_expenses": total_expenses,
        "remaining_balance": savings,
        "savings": savings,
        "savings_percentage": savings_percentage,
        "transaction_count": len(expenses),
        "category_totals": category_totals,
        "highest_category": highest_category,
        "recent_expenses": [
            expense_to_dict(e)
            for e in recent
        ],
    }


# ============================================================
# BUDGET
# ============================================================

def budget_data(month):
    summary = build_summary(month)

    income = summary["income"]
    actual = summary["category_totals"]

    rows = []

    for category, percentage in BUDGET_RULES.items():

        recommended = round(
            income * percentage / 100,
            2
        )

        spent = actual.get(
            category,
            0
        )

        difference = round(
            recommended - spent,
            2
        )

        rows.append({
            "category": category,
            "percentage": percentage,
            "recommended": recommended,
            "spent": spent,
            "difference": difference,
            "overspending": (
                spent > recommended
                and recommended > 0
            ),
        })

    return rows


# ============================================================
# RULE-BASED FINANCIAL ADVISOR
# ============================================================

def rule_based_advice(month):
    summary = build_summary(month)
    rows = budget_data(month)

    advice = []

    if summary["income"] <= 0:
        return [
            "Add your monthly income to receive personalized budget and savings guidance."
        ]

    if summary["savings"] < 0:
        advice.append(
            f"Your expenses are ₹{abs(summary['savings']):,.2f} "
            f"higher than your income this month. Review the "
            f"largest discretionary categories first."
        )

    elif summary["savings_percentage"] < 10:
        advice.append(
            f"You currently save ₹{summary['savings']:,.2f} "
            f"per month ({summary['savings_percentage']:.1f}%). "
            f"Consider setting a small automatic savings target "
            f"before discretionary spending."
        )

    else:
        advice.append(
            f"You currently save ₹{summary['savings']:,.2f} "
            f"per month ({summary['savings_percentage']:.1f}%). "
            f"Maintaining this habit can help build a stronger "
            f"financial buffer."
        )

    overspent = [
        row
        for row in rows
        if row["overspending"]
    ]

    overspent.sort(
        key=lambda r: (
            r["spent"] - r["recommended"]
        ),
        reverse=True
    )

    for row in overspent[:3]:

        extra = (
            row["spent"]
            - row["recommended"]
        )

        advice.append(
            f"You spent ₹{row['spent']:,.2f} on "
            f"{row['category'].lower()}, which is "
            f"₹{extra:,.2f} above the suggested limit "
            f"of ₹{row['recommended']:,.2f}."
        )

    if not overspent:
        advice.append(
            "Your tracked categories are within the simple "
            "suggested monthly limits this month."
        )

    if summary["highest_category"]:

        category = summary["highest_category"]

        advice.append(
            f"Your highest spending category is "
            f"{category} at "
            f"₹{summary['category_totals'][category]:,.2f}. "
            f"Review that category if you want to increase savings."
        )

    return advice[:5]


# ============================================================
# OPTIONAL AI ADVISOR
# ============================================================

def ai_advice(month):
    api_key = (
        os.getenv("AI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )

    if not api_key:
        return {
            "mode": "rule-based",
            "advice": rule_based_advice(month)
        }

    endpoint = os.getenv(
        "AI_API_URL",
        "https://api.openai.com/v1/chat/completions"
    )

    model = os.getenv(
        "AI_MODEL",
        "gpt-4o-mini"
    )

    summary = build_summary(month)
    rows = budget_data(month)

    prompt = (
        "You are a financial education assistant. "
        "Give concise, non-professional financial guidance "
        "based only on the supplied monthly data. "
        "Do not claim certainty. Return 3-5 bullet-style "
        "recommendations in plain text.\n\n"

        f"Income: ₹{summary['income']:.2f}\n"
        f"Expenses: ₹{summary['total_expenses']:.2f}\n"
        f"Savings: ₹{summary['savings']:.2f}\n"
        f"Savings percentage: "
        f"{summary['savings_percentage']:.1f}%\n"
        f"Category spending: "
        f"{summary['category_totals']}\n"
        f"Budget comparison: {rows}"
    )

    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You provide general financial education, "
                            "not regulated financial advice."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.3,
            },
            timeout=20,
        )

        response.raise_for_status()

        payload = response.json()

        content = (
            payload["choices"][0]["message"]["content"]
            .strip()
        )

        if content:
            return {
                "mode": "api",
                "advice": [
                    line.lstrip("-• ").strip()
                    for line in content.splitlines()
                    if line.strip()
                ],
            }

    except Exception:
        pass

    return {
        "mode": "rule-based fallback",
        "advice": rule_based_advice(month)
    }


# ============================================================
# AUTHENTICATION ROUTES
# ============================================================

@app.route("/setup", methods=["GET", "POST"])
def setup():
    """
    First-time setup.

    This page only works when there are zero users.
    The first account becomes the administrator.
    """

    if User.query.count() > 0:
        return redirect(url_for("login"))

    if request.method == "POST":

        try:
            name = validate_name(
                request.form.get("name")
            )

            email = normalize_email(
                request.form.get("email")
            )

            password = validate_password(
                request.form.get("password")
            )

            confirm_password = str(
                request.form.get("confirm_password")
                or ""
            )

            if password != confirm_password:
                raise ValueError(
                    "Passwords do not match."
                )

            admin = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(
                    password
                ),
                role="admin",
                is_active=True,
            )

            db.session.add(admin)
            db.session.commit()

            login_user(admin)

            return redirect(url_for("index"))

        except ValueError as exc:
            db.session.rollback()

            return render_template(
                "setup.html",
                error=str(exc)
            )

        except Exception:
            db.session.rollback()

            return render_template(
                "setup.html",
                error="Unable to create administrator account."
            )

    return render_template(
        "setup.html"
    )


@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if User.query.count() == 0:
        return redirect(url_for("setup"))

    if request.method == "POST":

        email = str(
            request.form.get("email")
            or ""
        ).strip().lower()

        password = str(
            request.form.get("password")
            or ""
        )

        user = User.query.filter_by(
            email=email
        ).first()

        if not user:
            return render_template(
                "login.html",
                error="Invalid email or password."
            )

        if not user.is_active:
            return render_template(
                "login.html",
                error="Your account has been disabled."
            )

        if not check_password_hash(
            user.password_hash,
            password
        ):
            return render_template(
                "login.html",
                error="Invalid email or password."
            )

        login_user(user)

        next_url = request.args.get("next")

        if (
            next_url
            and next_url.startswith("/")
            and not next_url.startswith("//")
        ):
            return redirect(next_url)

        return redirect(url_for("index"))

    return render_template(
        "login.html"
    )


@app.get("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():

    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if User.query.count() == 0:
        return redirect(url_for("setup"))

    if request.method == "POST":

        try:
            name = validate_name(
                request.form.get("name")
            )

            email = normalize_email(
                request.form.get("email")
            )

            password = validate_password(
                request.form.get("password")
            )

            confirm_password = str(
                request.form.get("confirm_password")
                or ""
            )

            if password != confirm_password:
                raise ValueError(
                    "Passwords do not match."
                )

            existing = User.query.filter_by(
                email=email
            ).first()

            if existing:
                raise ValueError(
                    "An account with this email already exists."
                )

            user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(
                    password
                ),
                role="user",
                is_active=True,
            )

            db.session.add(user)
            db.session.commit()

            login_user(user)

            return redirect(
                url_for("index")
            )

        except ValueError as exc:
            db.session.rollback()

            return render_template(
                "signup.html",
                error=str(exc)
            )

        except Exception:
            db.session.rollback()

            return render_template(
                "signup.html",
                error="Unable to create account."
            )

    return render_template(
        "signup.html"
    )


# ============================================================
# ADMIN HELPERS
# ============================================================

def admin_required(view):
    """
    Protects routes that require administrator privileges.
    """

    from functools import wraps

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):

        if current_user.role != "admin":
            if request.path.startswith("/api/"):
                return jsonify({
                    "ok": False,
                    "error": "Administrator access required."
                }), 403

            return (
                render_template(
                    "login.html",
                    error="Administrator access required."
                ),
                403
            )

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# ADMIN USER MANAGEMENT
# ============================================================

@app.get("/admin")
@admin_required
def admin_users():

    users = User.query.order_by(
        User.created_at.desc(),
        User.id.desc()
    ).all()

    return render_template(
        "admin_users.html",
        users=users
    )


@app.post("/admin/users/create")
@admin_required
def admin_create_user():

    try:
        name = validate_name(
            request.form.get("name")
        )

        email = normalize_email(
            request.form.get("email")
        )

        password = validate_password(
            request.form.get("password")
        )

        role = str(
            request.form.get("role")
            or "user"
        ).strip().lower()

        if role not in {"admin", "user"}:
            raise ValueError(
                "Invalid user role."
            )

        existing = User.query.filter_by(
            email=email
        ).first()

        if existing:
            raise ValueError(
                "An account with this email already exists."
            )

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(
                password
            ),
            role=role,
            is_active=True,
        )

        db.session.add(user)
        db.session.commit()

        return redirect(
            url_for("admin_users")
        )

    except ValueError as exc:
        db.session.rollback()

        users = User.query.order_by(
            User.created_at.desc(),
            User.id.desc()
        ).all()

        return render_template(
            "admin_users.html",
            users=users,
            error=str(exc)
        )

    except Exception:
        db.session.rollback()

        users = User.query.order_by(
            User.created_at.desc(),
            User.id.desc()
        ).all()

        return render_template(
            "admin_users.html",
            users=users,
            error="Unable to create user."
        )


@app.post("/admin/users/<int:user_id>/toggle")
@admin_required
def admin_toggle_user(user_id):

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return redirect(
            url_for("admin_users")
        )

    # An administrator cannot disable their own account.
    if user.id == current_user.id:
        return redirect(
            url_for("admin_users")
        )

    user.is_active = not user.is_active

    db.session.commit()

    return redirect(
        url_for("admin_users")
    )


@app.post("/admin/users/<int:user_id>/role")
@admin_required
def admin_change_role(user_id):

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return redirect(
            url_for("admin_users")
        )

    new_role = str(
        request.form.get("role")
        or ""
    ).strip().lower()

    if new_role not in {"admin", "user"}:
        return redirect(
            url_for("admin_users")
        )

    # Do not allow the current administrator
    # to accidentally remove their own admin access.
    if user.id == current_user.id:
        return redirect(
            url_for("admin_users")
        )

    user.role = new_role

    db.session.commit()

    return redirect(
        url_for("admin_users")
    )


@app.post("/admin/users/<int:user_id>/delete")
@admin_required
def admin_delete_user(user_id):

    user = db.session.get(
        User,
        user_id
    )

    if not user:
        return redirect(
            url_for("admin_users")
        )

    # Never allow an administrator to delete themselves.
    if user.id == current_user.id:
        return redirect(
            url_for("admin_users")
        )

    db.session.delete(user)
    db.session.commit()

    return redirect(
        url_for("admin_users")
    )


# ============================================================
# MAIN DASHBOARD
# ============================================================

@app.route("/")
@login_required
def index():

    return render_template(
        "index.html",
        categories=CATEGORIES,
        current_month=current_month(),
        current_user=current_user
    )


# ============================================================
# DASHBOARD API
# ============================================================

@app.get("/api/dashboard")
@login_required
def dashboard_api():

    try:
        month = get_month_from_request()

        return jsonify({
            "ok": True,
            **build_summary(month)
        })

    except ValueError as exc:

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400


# ============================================================
# INCOME API
# ============================================================

@app.get("/api/income")
@login_required
def get_income():

    try:
        month = get_month_from_request()

        row = Income.query.filter_by(
            month=month,
            user_id=current_user.id
        ).first()

        return jsonify({
            "ok": True,
            "month": month,
            "amount": (
                money(row.amount)
                if row
                else 0
            )
        })

    except ValueError as exc:

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400


@app.post("/api/income")
@login_required
def save_income():

    try:

        data = (
            request.get_json(silent=True)
            or request.form
        )

        amount = parse_amount(
            data.get("amount")
        )

        month = (
            data.get("month")
            or current_month()
        )

        datetime.strptime(
            month,
            "%Y-%m"
        )

        row = Income.query.filter_by(
            month=month,
            user_id=current_user.id
        ).first()

        if row:

            row.amount = amount
            row.updated_at = datetime.utcnow()

        else:

            row = Income(
                amount=amount,
                month=month,
                user_id=current_user.id
            )

            db.session.add(row)

        db.session.commit()

        return jsonify({
            "ok": True,
            "message": "Income saved successfully.",
            "amount": money(amount),
            "month": month
        })

    except (ValueError, TypeError) as exc:

        db.session.rollback()

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400

    except Exception:

        db.session.rollback()

        return jsonify({
            "ok": False,
            "error": "Unable to save income."
        }), 500


# ============================================================
# EXPENSE API
# ============================================================

@app.get("/api/expenses")
@login_required
def list_expenses():

    try:

        month = get_month_from_request()

        query = month_expenses(month)

        category = request.args.get(
            "category"
        )

        start = request.args.get(
            "start"
        )

        end = request.args.get(
            "end"
        )

        if category and category in CATEGORIES:
            query = query.filter_by(
                category=category
            )

        if start:
            query = query.filter(
                Expense.date >= parse_date(start)
            )

        if end:
            query = query.filter(
                Expense.date <= parse_date(end)
            )

        expenses = query.order_by(
            Expense.date.desc(),
            Expense.id.desc()
        ).all()

        return jsonify({
            "ok": True,
            "expenses": [
                expense_to_dict(e)
                for e in expenses
            ]
        })

    except ValueError as exc:

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400


@app.post("/api/expenses")
@login_required
def create_expense():

    try:

        data = (
            request.get_json(silent=True)
            or request.form
        )

        amount = parse_amount(
            data.get("amount")
        )

        category = str(
            data.get("category", "")
        ).strip()

        description = str(
            data.get("description", "")
        ).strip()

        expense_date = parse_date(
            data.get("date")
        )

        if category not in CATEGORIES:
            raise ValueError(
                "Please choose a valid category."
            )

        if not description:
            raise ValueError(
                "Description is required."
            )

        if len(description) > 255:
            raise ValueError(
                "Description must be 255 characters or fewer."
            )

        expense = Expense(
            amount=amount,
            category=category,
            description=description,
            date=expense_date,
            user_id=current_user.id
        )

        db.session.add(expense)
        db.session.commit()

        return jsonify({
            "ok": True,
            "message": "Expense added.",
            "expense": expense_to_dict(expense)
        })

    except (ValueError, TypeError) as exc:

        db.session.rollback()

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400

    except Exception:

        db.session.rollback()

        return jsonify({
            "ok": False,
            "error": "Unable to add expense."
        }), 500


@app.delete("/api/expenses/<int:expense_id>")
@login_required
def delete_expense(expense_id):

    expense = db.session.get(
        Expense,
        expense_id
    )

    # IMPORTANT:
    # The expense must belong to the logged-in user.
    if (
        not expense
        or expense.user_id != current_user.id
    ):
        return jsonify({
            "ok": False,
            "error": "Expense not found."
        }), 404

    try:

        db.session.delete(expense)
        db.session.commit()

        return jsonify({
            "ok": True,
            "message": "Expense deleted."
        })

    except Exception:

        db.session.rollback()

        return jsonify({
            "ok": False,
            "error": "Unable to delete expense."
        }), 500


# ============================================================
# BUDGET API
# ============================================================

@app.get("/api/budget")
@login_required
def budget_api():

    try:

        month = get_month_from_request()

        return jsonify({
            "ok": True,
            "rows": budget_data(month),
            "income": build_summary(month)["income"]
        })

    except ValueError as exc:

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400


# ============================================================
# ADVISOR API
# ============================================================

@app.get("/api/advice")
@login_required
def advice_api():

    try:

        month = get_month_from_request()

        result = ai_advice(month)

        return jsonify({
            "ok": True,
            **result
        })

    except ValueError as exc:

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400


# ============================================================
# SUMMARY API
# ============================================================

@app.get("/api/summary")
@login_required
def summary_api():

    try:

        month = get_month_from_request()

        summary = build_summary(month)

        summary["overspending"] = [
            row
            for row in budget_data(month)
            if row["overspending"]
        ]

        summary["recommendations"] = (
            rule_based_advice(month)
        )

        return jsonify({
            "ok": True,
            **summary
        })

    except ValueError as exc:

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 400


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith("/api/"):
        return jsonify({
            "ok": False,
            "error": "Not found."
        }), 404

    if not current_user.is_authenticated:
        return redirect(
            url_for("login")
        )

    return render_template(
        "index.html",
        categories=CATEGORIES,
        current_month=current_month(),
        current_user=current_user
    ), 404


@app.errorhandler(500)
def server_error(error):

    db.session.rollback()

    if request.path.startswith("/api/"):
        return jsonify({
            "ok": False,
            "error": "Internal server error."
        }), 500

    return (
        "Internal server error",
        500
    )


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

with app.app_context():

    # First create any missing tables, including User.
    db.create_all()

    # Then safely update the existing PostgreSQL
    # income/expense tables.
    migrate_database()


# ============================================================
# DEVELOPMENT SERVER
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.getenv(
            "FLASK_DEBUG",
            "0"
        ) == "1"
    )