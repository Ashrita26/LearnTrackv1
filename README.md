# LearnTrack – Skill Tracker (Python Full Stack Project)

A full stack web application built during the ApexPlanet Python Full Stack Development internship.
Users create an account, record the skills they are learning, set a level and progress, and manage them
from a responsive dashboard. Everything is also available through a JSON REST API.

**Stack:** Python 3 · Flask · SQLite (SQL) · HTML5 · CSS3 · JavaScript · Jinja2 templates

## Modules (as listed in the internship report)
| Module | Where |
|---|---|
| Registration, login, logout with hashed passwords | `app.py` (`/register`, `/login`, `/logout`) |
| CRUD on records (skills) | `/skills/new`, `/skills/<id>/edit`, `/skills/<id>/delete` |
| Dynamic pages from the database | `templates/` (Jinja2) |
| REST API returning JSON (test with Postman) | `/api/...` |
| Responsive UI + client-side validation | `static/css/style.css`, `static/js/main.js` |
| SQL schema | `schema.sql` |
| Version control | Git / GitHub (see below) |

## Run it
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # open http://127.0.0.1:5000
```
Set a real secret before deploying: `export SECRET_KEY="something-long-and-random"`.

## Run the tests
```bash
python -m unittest discover -s tests -v
```

## REST API
Log in first; the session cookie is kept by Postman. Write requests must use `Content-Type: application/json`.

| Method | URL | Body (JSON) | Result |
|---|---|---|---|
| POST | `/api/register` | `username, email, password` | 201 |
| POST | `/api/login` | `identifier, password` | 200 |
| POST | `/api/logout` | – | 200 |
| GET | `/api/skills` | – | list of your skills |
| POST | `/api/skills` | `name, category, level, progress, notes` | 201 |
| GET | `/api/skills/<id>` | – | one skill / 404 |
| PUT | `/api/skills/<id>` | any fields to change | updated skill |
| DELETE | `/api/skills/<id>` | – | 204 |

`level` is `Beginner`, `Intermediate` or `Advanced`; `progress` is 0–100.

Example:
```bash
curl -c jar -H "Content-Type: application/json" -d '{"identifier":"asha","password":"password123"}' localhost:5000/api/login
curl -b jar -H "Content-Type: application/json" -d '{"name":"Flask","level":"Intermediate","progress":60}' localhost:5000/api/skills
```

## Project structure
```
learntrack/
├── app.py            # routes, validation, API, database access
├── schema.sql        # users and skills tables
├── templates/        # base, home, auth, dashboard, skill form, error
├── static/css|js/    # styling and client-side behaviour
├── tests/test_app.py # 9 automated tests
└── requirements.txt
```

## Security notes
Passwords are hashed (Werkzeug); all SQL uses parameters; templates auto-escape output; form posts use a CSRF token;
the API only accepts JSON for writes; each user can only see and change their own skills.

## Push to GitHub
```bash
git init && git add . && git commit -m "LearnTrack: initial version"
git branch -M main
git remote add origin https://github.com/<your-username>/learntrack.git
git push -u origin main
```
