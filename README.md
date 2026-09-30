# Personal Finance Advisor Bot

A simple full-stack course project for tracking monthly income and expenses, calculating savings, comparing spending with a basic budget, and generating understandable financial guidance.

> **Educational use:** This application provides general budgeting guidance and is not professional financial, investment, tax, or legal advice.

## Features

- Responsive dashboard with monthly income, expenses, savings, savings percentage and transaction count.
- Expense tracking with amount, category, description and date.
- Expense deletion and category/date filtering.
- SQLite database through SQLAlchemy.
- Automatic database/table creation on startup.
- Category-wise expense breakdown chart.
- Simple budget advisor with recommended category limits and overspending warnings.
- Monthly summary with highest spending category and recommendations.
- AI Financial Advisor interface with an optional server-side AI API integration.
- Reliable rule-based advisor when no API key is configured.
- Server-side validation and JSON API error handling.
- Production-compatible Gunicorn startup command.

## Tech stack

- **Backend:** Python, Flask, Flask-SQLAlchemy
- **Database:** SQLite locally; PostgreSQL can be used in production through `DATABASE_URL`
- **Frontend:** HTML, CSS, JavaScript
- **Chart:** Chart.js via CDN
- **Optional AI:** OpenAI-compatible Chat Completions endpoint configured only on the server
- **Deployment:** Gunicorn + Render (or another Python hosting provider)

## Project structure

```text
personal-finance-advisor/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .env.example
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── script.js
└── instance/
    └── finance.db        # created automatically after first run; ignored by Git
```

## Run locally

### 1. Create and enter a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables (optional)

Copy `.env.example` to `.env`.

For normal course-project use, you can leave the AI settings empty. The application will use its built-in rule-based advisor.

If you have an OpenAI-compatible API key, set:

```env
AI_API_KEY=your-secret-key
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_MODEL=gpt-4o-mini
```

The key is read only by Flask on the server. It is never placed in frontend JavaScript.

### 4. Start the app

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

The SQLite database is automatically created at `instance/finance.db`.

## Example usage

1. Select the current month.
2. Save a monthly income such as `20000`.
3. Add expenses such as:
   - Food — ₹2,500 — Groceries
   - Rent — ₹6,000 — Monthly rent
   - Transport — ₹1,000 — Bus and fuel
   - Entertainment — ₹1,500 — Movies and subscriptions
4. Open **Dashboard** to see savings and the category chart.
5. Open **Budget Advisor** to compare actual spending with suggested limits.
6. Open **AI Financial Advisor** and click **Generate Advice**. Without an API key, the rule-based advisor still analyzes the real database values.
7. Open **Monthly Summary** for the report-style view.

## API endpoints

- `GET /api/dashboard?month=YYYY-MM`
- `GET /api/income?month=YYYY-MM`
- `POST /api/income`
- `GET /api/expenses?month=YYYY-MM`
- `POST /api/expenses`
- `DELETE /api/expenses/<id>`
- `GET /api/budget?month=YYYY-MM`
- `GET /api/advice?month=YYYY-MM`
- `GET /api/summary?month=YYYY-MM`

## Deployment on Render

### Recommended production database

For a live demo, use a PostgreSQL database on Render rather than relying on a local SQLite file. SQLite is excellent for the course project locally, but an ephemeral server filesystem should not be treated as durable production storage.

1. Push the project to GitHub.
2. In Render, create a **PostgreSQL** database.
3. Create a new **Web Service** and connect your GitHub repository.
4. Build command:

```bash
pip install -r requirements.txt
```

5. Start command:

```bash
gunicorn app:app
```

6. Add environment variables in Render:

```text
SECRET_KEY=<long-random-secret>
DATABASE_URL=<Render PostgreSQL connection string>
```

7. Optionally add `AI_API_KEY`, `AI_API_URL`, and `AI_MODEL` if you want the external AI advisor enabled.
8. Deploy. Render will provide a public `onrender.com` URL that you can share with your mentor.

### Important deployment note

The app automatically creates database tables when it starts. It does not run migrations, which keeps this course project simple. If you later change database columns, use a migration tool such as Alembic/Flask-Migrate rather than changing a live database blindly.

## Push to GitHub

From the project folder:

```bash
git init
git add .
git commit -m "Initial Personal Finance Advisor Bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/personal-finance-advisor.git
git push -u origin main
```

Do **not** commit `.env` or the SQLite database. They are ignored by `.gitignore`.

## Security notes

- API keys are server-side environment variables only.
- User input is validated before it is written to the database.
- Amounts must be positive and within a reasonable database range.
- Expense categories are checked against the allowed category list.
- Empty descriptions and invalid dates are rejected.
- The frontend escapes text before inserting user-provided values into HTML.
- For a real multi-user production product, add authentication, authorization, CSRF protection, rate limiting, migrations and per-user data isolation. Those are intentionally outside this simple course MVP.
