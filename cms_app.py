from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cms.sqlite3"
SECRET_KEY = os.environ.get("CMS_SECRET_KEY", "change-me-in-production")

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    with open(BASE_DIR / "schema.sql", "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()
    db.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def home():
    return redirect(url_for("dashboard" if session.get("user_id") else "login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    db = get_db()
    has_users = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    if has_users > 0:
        flash("Setup já finalizado. Faça login.", "info")
        return redirect(url_for("login"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        if not email or len(password) < 8:
            flash("Informe um e-mail e senha com no mínimo 8 caracteres.", "danger")
            return render_template("setup.html")

        db.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), now_iso()),
        )
        db.commit()
        flash("Administrador criado. Faça login para continuar.", "success")
        return redirect(url_for("login"))

    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    has_users = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    if has_users == 0:
        flash("Crie o administrador primeiro.", "warning")
        return redirect(url_for("setup"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    sites = db.execute("SELECT * FROM sites ORDER BY created_at DESC").fetchall()
    return render_template("dashboard.html", sites=sites)


@app.route("/sites/new", methods=["POST"])
@login_required
def create_site():
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip().lower()
    if not name or not slug:
        flash("Nome e slug são obrigatórios.", "danger")
        return redirect(url_for("dashboard"))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO sites (name, slug, created_at) VALUES (?, ?, ?)",
            (name, slug, now_iso()),
        )
        db.commit()
        flash("Site criado com sucesso.", "success")
    except sqlite3.IntegrityError:
        flash("Slug já está em uso.", "danger")

    return redirect(url_for("dashboard"))


@app.route("/sites/<int:site_id>")
@login_required
def site_detail(site_id: int):
    db = get_db()
    site = db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    if site is None:
        abort(404)
    pages = db.execute(
        "SELECT * FROM pages WHERE site_id = ? ORDER BY updated_at DESC", (site_id,)
    ).fetchall()
    return render_template("site_detail.html", site=site, pages=pages)


@app.route("/sites/<int:site_id>/pages/new", methods=["POST"])
@login_required
def create_page(site_id: int):
    db = get_db()
    site = db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    if site is None:
        abort(404)

    title = request.form.get("title", "").strip()
    slug = request.form.get("slug", "").strip().lower()
    content = request.form.get("content", "").strip()
    status = request.form.get("status", "draft").strip()

    if not title or not slug:
        flash("Título e slug são obrigatórios.", "danger")
        return redirect(url_for("site_detail", site_id=site_id))

    try:
        db.execute(
            """
            INSERT INTO pages (site_id, title, slug, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (site_id, title, slug, content, status, now_iso(), now_iso()),
        )
        db.commit()
        flash("Página criada.", "success")
    except sqlite3.IntegrityError:
        flash("Já existe uma página com esse slug neste site.", "danger")

    return redirect(url_for("site_detail", site_id=site_id))


@app.route("/pages/<int:page_id>/edit", methods=["GET", "POST"])
@login_required
def edit_page(page_id: int):
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if page is None:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip().lower()
        content = request.form.get("content", "").strip()
        status = request.form.get("status", "draft").strip()

        if not title or not slug:
            flash("Título e slug são obrigatórios.", "danger")
            return render_template("edit_page.html", page=page)

        try:
            db.execute(
                """
                UPDATE pages
                SET title = ?, slug = ?, content = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, slug, content, status, now_iso(), page_id),
            )
            db.commit()
            flash("Página atualizada.", "success")
            return redirect(url_for("site_detail", site_id=page["site_id"]))
        except sqlite3.IntegrityError:
            flash("Slug já está em uso neste site.", "danger")

    return render_template("edit_page.html", page=page)


@app.route("/pages/<int:page_id>/delete", methods=["POST"])
@login_required
def delete_page(page_id: int):
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if page is None:
        abort(404)

    db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
    db.commit()
    flash("Página removida.", "info")
    return redirect(url_for("site_detail", site_id=page["site_id"]))


@app.get("/api/sites/<site_slug>/pages/<page_slug>")
def get_page(site_slug: str, page_slug: str):
    db = get_db()
    page = db.execute(
        """
        SELECT pages.*, sites.slug AS site_slug, sites.name AS site_name
        FROM pages
        JOIN sites ON sites.id = pages.site_id
        WHERE sites.slug = ? AND pages.slug = ? AND pages.status = 'published'
        """,
        (site_slug, page_slug),
    ).fetchone()

    if page is None:
        return jsonify({"error": "Not found"}), 404

    return jsonify(
        {
            "site": {"slug": page["site_slug"], "name": page["site_name"]},
            "page": {
                "title": page["title"],
                "slug": page["slug"],
                "content": page["content"],
                "updated_at": page["updated_at"],
            },
        }
    )


if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)
