"""LearnTrack - a skill tracker built with Flask, SQLite, HTML/CSS/JavaScript.

Modules: registration / login / logout, CRUD on skills, template-rendered
pages from the database, a JSON REST API, and a responsive interface.
"""
import os
import re
import secrets
import sqlite3
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

LEVELS = ("Beginner", "Intermediate", "Advanced")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.path.join(app.instance_path, "learntrack.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    # ---------------------------------------------------------- database
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        with app.open_resource("schema.sql") as f:
            get_db().executescript(f.read().decode("utf8"))

    with app.app_context():
        init_db()

    @app.cli.command("init-db")
    def init_db_command():
        """Create the tables (safe to run repeatedly)."""
        init_db()
        print("Database ready.")

    # ----------------------------------------------------------- helpers
    @app.before_request
    def load_user():
        uid = session.get("user_id")
        g.user = None
        if uid is not None:
            g.user = get_db().execute(
                "SELECT id, username, email FROM users WHERE id = ?", (uid,)
            ).fetchone()

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def check_csrf():
        """Form posts need a token; the JSON API requires application/json,
        which a cross-site HTML form cannot send."""
        if request.method == "POST" and not request.path.startswith("/api/"):
            token = session.get("_csrf")
            if not token or token != request.form.get("_csrf"):
                abort(400, "Invalid or missing CSRF token.")

    def login_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                return redirect(url_for("login", next=request.path))
            return view(*a, **kw)
        return wrapped

    def api_login_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                return jsonify(error="Authentication required."), 401
            return view(*a, **kw)
        return wrapped

    def validate_skill(data):
        """Return (clean_dict, errors_list)."""
        errors = []
        name = (data.get("name") or "").strip()
        category = (data.get("category") or "General").strip() or "General"
        level = data.get("level") or "Beginner"
        notes = (data.get("notes") or "").strip()
        try:
            progress = int(data.get("progress", 0))
        except (TypeError, ValueError):
            progress = -1
        if not name or len(name) > 80:
            errors.append("Skill name is required (max 80 characters).")
        if len(category) > 40:
            errors.append("Category must be at most 40 characters.")
        if level not in LEVELS:
            errors.append("Level must be Beginner, Intermediate or Advanced.")
        if not 0 <= progress <= 100:
            errors.append("Progress must be a number from 0 to 100.")
        if len(notes) > 500:
            errors.append("Notes must be at most 500 characters.")
        return dict(name=name, category=category, level=level,
                    progress=progress, notes=notes), errors

    def get_skill(skill_id):
        row = get_db().execute(
            "SELECT * FROM skills WHERE id = ? AND user_id = ?",
            (skill_id, g.user["id"])).fetchone()
        return row

    def validate_signup(username, email, password):
        errors = []
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username or ""):
            errors.append("Username must be 3-20 letters, digits or underscores.")
        if not EMAIL_RE.match(email or ""):
            errors.append("Enter a valid email address.")
        if len(password or "") < 8:
            errors.append("Password must be at least 8 characters.")
        return errors

    def create_user(username, email, password):
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email.lower(), generate_password_hash(password)))
            db.commit()
            return cur.lastrowid, None
        except sqlite3.IntegrityError:
            return None, "That username or email is already registered."

    def authenticate(identifier, password):
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (identifier, (identifier or "").lower())).fetchone()
        if user and check_password_hash(user["password_hash"], password or ""):
            return user
        return None

    # ------------------------------------------------------- web: auth
    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            errors = validate_signup(username, email, password)
            if not errors:
                uid, err = create_user(username, email, password)
                if err:
                    errors.append(err)
                else:
                    session.clear()
                    session["user_id"] = uid
                    flash("Welcome to LearnTrack! Add your first skill.", "success")
                    return redirect(url_for("dashboard"))
            for e in errors:
                flash(e, "error")
        return render_template("register.html")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if request.method == "POST":
            user = authenticate(request.form.get("identifier", "").strip(),
                                request.form.get("password", ""))
            if user:
                session.clear()
                session["user_id"] = user["id"]
                nxt = request.args.get("next", "")
                if not nxt.startswith("/") or nxt.startswith("//"):
                    nxt = url_for("dashboard")
                return redirect(nxt)
            flash("Invalid username/email or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=("POST",))
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("index"))

    # ------------------------------------------------- web: skills CRUD
    @app.route("/dashboard")
    @login_required
    def dashboard():
        q = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        sql = "SELECT * FROM skills WHERE user_id = ?"
        params = [g.user["id"]]
        if q:
            sql += " AND (name LIKE ? OR notes LIKE ?)"
            params += [f"%{q}%", f"%{q}%"]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY updated_at DESC, id DESC"
        db = get_db()
        skills = db.execute(sql, params).fetchall()
        stats = db.execute(
            "SELECT COUNT(*) AS total, COALESCE(ROUND(AVG(progress)), 0) AS avg, "
            "COALESCE(SUM(progress = 100), 0) AS done FROM skills WHERE user_id = ?",
            (g.user["id"],)).fetchone()
        categories = [r["category"] for r in db.execute(
            "SELECT DISTINCT category FROM skills WHERE user_id = ? ORDER BY category",
            (g.user["id"],))]
        return render_template("dashboard.html", skills=skills, stats=stats,
                               categories=categories, q=q, category=category)

    @app.route("/skills/new", methods=("GET", "POST"))
    @login_required
    def skill_create():
        form = {"level": "Beginner", "progress": 0, "category": "General"}
        if request.method == "POST":
            form, errors = validate_skill(request.form)
            if not errors:
                db = get_db()
                db.execute(
                    "INSERT INTO skills (user_id, name, category, level, progress, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (g.user["id"], form["name"], form["category"], form["level"],
                     form["progress"], form["notes"]))
                db.commit()
                flash("Skill added.", "success")
                return redirect(url_for("dashboard"))
            for e in errors:
                flash(e, "error")
        return render_template("skill_form.html", skill=form, levels=LEVELS,
                               title="Add a skill")

    @app.route("/skills/<int:skill_id>/edit", methods=("GET", "POST"))
    @login_required
    def skill_edit(skill_id):
        skill = get_skill(skill_id)
        if skill is None:
            abort(404)
        if request.method == "POST":
            form, errors = validate_skill(request.form)
            if not errors:
                db = get_db()
                db.execute(
                    "UPDATE skills SET name=?, category=?, level=?, progress=?, notes=?, "
                    "updated_at=datetime('now') WHERE id=? AND user_id=?",
                    (form["name"], form["category"], form["level"], form["progress"],
                     form["notes"], skill_id, g.user["id"]))
                db.commit()
                flash("Skill updated.", "success")
                return redirect(url_for("dashboard"))
            for e in errors:
                flash(e, "error")
            skill = form
        return render_template("skill_form.html", skill=skill, levels=LEVELS,
                               title="Edit skill")

    @app.route("/skills/<int:skill_id>/delete", methods=("POST",))
    @login_required
    def skill_delete(skill_id):
        if get_skill(skill_id) is None:
            abort(404)
        db = get_db()
        db.execute("DELETE FROM skills WHERE id = ? AND user_id = ?",
                   (skill_id, g.user["id"]))
        db.commit()
        flash("Skill deleted.", "success")
        return redirect(url_for("dashboard"))

    # --------------------------------------------------------- REST API
    def json_body():
        if not request.is_json:
            return None
        return request.get_json(silent=True)

    @app.route("/api/register", methods=("POST",))
    def api_register():
        data = json_body()
        if not isinstance(data, dict):
            return jsonify(error="Send a JSON object with Content-Type: application/json."), 415
        errors = validate_signup(data.get("username", ""), data.get("email", ""),
                                 data.get("password", ""))
        if errors:
            return jsonify(errors=errors), 400
        uid, err = create_user(data["username"].strip(), data["email"].strip(), data["password"])
        if err:
            return jsonify(error=err), 409
        return jsonify(id=uid, username=data["username"].strip()), 201

    @app.route("/api/login", methods=("POST",))
    def api_login():
        data = json_body()
        if not isinstance(data, dict):
            return jsonify(error="Send a JSON object with Content-Type: application/json."), 415
        user = authenticate((data.get("identifier") or "").strip(), data.get("password"))
        if not user:
            return jsonify(error="Invalid credentials."), 401
        session.clear()
        session["user_id"] = user["id"]
        return jsonify(message="Logged in.", username=user["username"])

    @app.route("/api/logout", methods=("POST",))
    def api_logout():
        session.clear()
        return jsonify(message="Logged out.")

    @app.route("/api/skills", methods=("GET",))
    @api_login_required
    def api_list():
        rows = get_db().execute(
            "SELECT * FROM skills WHERE user_id = ? ORDER BY id", (g.user["id"],)).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/skills", methods=("POST",))
    @api_login_required
    def api_create():
        data = json_body()
        if not isinstance(data, dict):
            return jsonify(error="Send a JSON object with Content-Type: application/json."), 415
        clean, errors = validate_skill(data)
        if errors:
            return jsonify(errors=errors), 400
        db = get_db()
        cur = db.execute(
            "INSERT INTO skills (user_id, name, category, level, progress, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["id"], clean["name"], clean["category"], clean["level"],
             clean["progress"], clean["notes"]))
        db.commit()
        return jsonify(dict(get_skill(cur.lastrowid))), 201

    @app.route("/api/skills/<int:skill_id>", methods=("GET",))
    @api_login_required
    def api_get(skill_id):
        row = get_skill(skill_id)
        if row is None:
            return jsonify(error="Skill not found."), 404
        return jsonify(dict(row))

    @app.route("/api/skills/<int:skill_id>", methods=("PUT",))
    @api_login_required
    def api_update(skill_id):
        row = get_skill(skill_id)
        if row is None:
            return jsonify(error="Skill not found."), 404
        data = json_body()
        if not isinstance(data, dict):
            return jsonify(error="Send a JSON object with Content-Type: application/json."), 415
        merged = {**dict(row), **data}
        clean, errors = validate_skill(merged)
        if errors:
            return jsonify(errors=errors), 400
        db = get_db()
        db.execute(
            "UPDATE skills SET name=?, category=?, level=?, progress=?, notes=?, "
            "updated_at=datetime('now') WHERE id=? AND user_id=?",
            (clean["name"], clean["category"], clean["level"], clean["progress"],
             clean["notes"], skill_id, g.user["id"]))
        db.commit()
        return jsonify(dict(get_skill(skill_id)))

    @app.route("/api/skills/<int:skill_id>", methods=("DELETE",))
    @api_login_required
    def api_delete(skill_id):
        if get_skill(skill_id) is None:
            return jsonify(error="Skill not found."), 404
        db = get_db()
        db.execute("DELETE FROM skills WHERE id = ? AND user_id = ?",
                   (skill_id, g.user["id"]))
        db.commit()
        return "", 204

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify(error=e.description), 400
        return render_template("error.html", code=400, message=e.description), 400

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
