# PeopleDesk Employee Management System

A Flask + MySQL employee management project with login, registration, dashboard, and employee CRUD screens.

## 1. Requirements
- Python 3.10 or newer
- MySQL Server running locally

## 2. Setup
Open a terminal in this folder and run:

```bash
python -m venv venv
```

Windows PowerShell:
```powershell
.\venv\Scripts\Activate.ps1
Copy-Item .env.example .env
pip install -r requirements.txt
```

Edit `.env` and set `DB_USER`, `DB_PASSWORD`, and `DB_NAME` to match your MySQL setup. `DB_PASSWORD` is the password for your MySQL account, not the website login password. The app creates the database and tables automatically, so the MySQL account needs permission to create the database and tables.

## 3. Run
```bash
python app.py
```
Then open http://127.0.0.1:5000 in Chrome.

## Notes
- Change `SECRET_KEY` to a long random value before using this outside local development.
- Website admin credentials are created using the Register page and are stored as password hashes.
- Do not share or commit your `.env` file.
