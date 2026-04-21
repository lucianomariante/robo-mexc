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
DB_PATH = BASE_DIR / "cms_massa_criativa.sqlite3"

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.config["SECRET_KEY"] = os.environ.get("CMS_SECRET_KEY", "troque-esta-chave-em-producao")


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("admin_id") is None:
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    if session.get("admin_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    db = get_db()
    admin_exists = db.execute("SELECT COUNT(*) total FROM admins").fetchone()["total"]
    if admin_exists:
        return redirect(url_for("login"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or len(password) < 8:
            flash("Informe e-mail válido e senha com pelo menos 8 caracteres.", "danger")
            return render_template("setup.html")

        db.execute(
            "INSERT INTO admins (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), utc_now()),
        )
        db.commit()
        flash("Administrador criado com sucesso.", "success")
        return redirect(url_for("login"))

    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    admin_exists = db.execute("SELECT COUNT(*) total FROM admins").fetchone()["total"]
    if not admin_exists:
        return redirect(url_for("setup"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        admin = db.execute("SELECT * FROM admins WHERE email = ?", (email,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_email"] = admin["email"]
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


@app.post("/sites")
@login_required
def create_site():
    db = get_db()
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip().lower()

    if not name or not slug:
        flash("Nome e slug são obrigatórios.", "danger")
        return redirect(url_for("dashboard"))

    try:
        db.execute(
            "INSERT INTO sites (name, slug, created_at) VALUES (?, ?, ?)",
            (name, slug, utc_now()),
        )
        db.commit()
        flash("Site criado.", "success")
    except sqlite3.IntegrityError:
        flash("Slug já cadastrado.", "danger")

    return redirect(url_for("dashboard"))


@app.get("/sites/<int:site_id>")
@login_required
def site_pages(site_id: int):
    db = get_db()
    site = db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    if site is None:
        abort(404)

    pages = db.execute(
        "SELECT * FROM pages WHERE site_id = ? ORDER BY updated_at DESC", (site_id,)
    ).fetchall()
    return render_template("site_pages.html", site=site, pages=pages)


@app.post("/sites/<int:site_id>/pages")
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
        return redirect(url_for("site_pages", site_id=site_id))

    try:
        db.execute(
            """
            INSERT INTO pages (site_id, title, slug, content, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (site_id, title, slug, content, status, utc_now(), utc_now()),
        )
        db.commit()
        flash("Página criada.", "success")
    except sqlite3.IntegrityError:
        flash("Já existe página com este slug neste site.", "danger")

    return redirect(url_for("site_pages", site_id=site_id))


@app.route("/pages/<int:page_id>", methods=["GET", "POST"])
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
                (title, slug, content, status, utc_now(), page_id),
            )
            db.commit()
            flash("Página atualizada.", "success")
            return redirect(url_for("site_pages", site_id=page["site_id"]))
        except sqlite3.IntegrityError:
            flash("Slug já em uso neste site.", "danger")

    return render_template("edit_page.html", page=page)


@app.post("/pages/<int:page_id>/delete")
@login_required
def delete_page(page_id: int):
    db = get_db()
    page = db.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if page is None:
        abort(404)

    db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
    db.commit()
    flash("Página removida.", "info")
    return redirect(url_for("site_pages", site_id=page["site_id"]))


@app.get("/api/v1/sites/<site_slug>/pages/<page_slug>")
def public_page(site_slug: str, page_slug: str):
    db = get_db()
    page = db.execute(
        """
        SELECT pages.*, sites.name AS site_name, sites.slug AS site_slug
        FROM pages
        JOIN sites ON sites.id = pages.site_id
        WHERE sites.slug = ? AND pages.slug = ? AND pages.status = 'published'
        """,
        (site_slug, page_slug),
    ).fetchone()

    if page is None:
        return jsonify({"error": "Página não encontrada"}), 404

    return jsonify(
        {
            "site": {"name": page["site_name"], "slug": page["site_slug"]},
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=True)
