"""Safari Tent Makers & Fabricators — website + backend (Flask + SQLite).

Customers register / log in, place orders (payment on delivery) and see their
order history. The owner uses /admin to manage orders, customers, messages,
job applications, referrals and to post new products / gallery photos.
"""
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE, "data"))
DB_PATH = os.path.join(DATA_DIR, "safari.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------------------------------------------------------- catalogue
with open(os.path.join(BASE, "catalog.json"), encoding="utf-8") as f:
    CATALOG = json.load(f)
CATS, POSTS, JOBS = CATALOG["cats"], CATALOG["posts"], CATALOG["jobs"]
CAT_BY_ID = {c["id"]: c for c in CATS}
CAT_INDEX = {c["id"]: i for i, c in enumerate(CATS)}
PRODUCTS = {}
for _i, _c in enumerate(CATS):
    for _it in _c["items"]:
        _pid = f'{_c["id"]}/{_it["id"]}'
        PRODUCTS[_pid] = {"id": _pid, "name": _it["name"], "desc": _it["desc"], "art": _it["art"],
                          "cat": _c["name"], "cat_id": _c["id"], "seed": _i, "img": None}

STATUSES = [("new", "New"), ("confirmed", "Confirmed"), ("in_production", "In production"),
            ("out_for_delivery", "Out for delivery"), ("delivered_paid", "Delivered & paid"),
            ("cancelled", "Cancelled")]
STATUS_LABEL = dict(STATUSES)

# ---------------------------------------------------------------- site config
SITE = {
    "name": os.environ.get("SITE_NAME", "Safari Tent Makers & Fabricators"),
    "short": os.environ.get("SITE_SHORT", "Safari Tents"),
    "phone": os.environ.get("SITE_PHONE", "+254 700 000 000"),
    "whatsapp": os.environ.get("SITE_WHATSAPP", "254700000000"),
    "email": os.environ.get("SITE_EMAIL", "info@example.co.ke"),
    "address": os.environ.get("SITE_ADDRESS", "Workshop address, Town, Kenya"),
    "hours": os.environ.get("SITE_HOURS", "Mon – Sat: 7:00 – 18:00"),
    "commission": os.environ.get("SITE_COMMISSION", "a commission on every completed order"),
}


def load_secret():
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(DATA_DIR, "secret_key")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as fh:
        fh.write(key)
    os.chmod(path, 0o600)
    return key


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret(),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)

# ------------------------------------------------------------------ database
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL,
  pw_hash TEXT NOT NULL, ref_code TEXT NOT NULL UNIQUE, referred_by INTEGER REFERENCES users(id),
  is_admin INTEGER NOT NULL DEFAULT 0, consent_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL, phone TEXT NOT NULL, location TEXT NOT NULL, delivery_date TEXT, extra TEXT,
  referrer_id INTEGER REFERENCES users(id), status TEXT NOT NULL DEFAULT 'new', admin_note TEXT,
  commission_paid INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_items(
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id TEXT, name TEXT NOT NULL, category TEXT, qty INTEGER NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT NOT NULL, phone TEXT NOT NULL, body TEXT NOT NULL,
  handled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT, role TEXT NOT NULL,
  body TEXT, handled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS new_products(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL,
  art TEXT, image TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gallery(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, cat_id TEXT NOT NULL, image TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def make_ref_code(con, name):
    ini = "".join(w[0] for w in re.findall(r"[A-Za-z]+", name))[:3].upper() or "REF"
    while True:
        code = f"{ini}-{secrets.randbelow(9000) + 1000}"
        if not con.execute("SELECT 1 FROM users WHERE ref_code=?", (code,)).fetchone():
            return code


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    # optional admin account from environment variables
    email, pw = os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD")
    if email and pw and len(pw) >= 8:
        email = email.strip().lower()
        row = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row:
            con.execute("UPDATE users SET is_admin=1 WHERE id=?", (row["id"],))
        else:
            con.execute(
                "INSERT INTO users(name,email,phone,pw_hash,ref_code,is_admin,created_at) VALUES(?,?,?,?,?,1,?)",
                ("Administrator", email, "0", generate_password_hash(pw), make_ref_code(con, "Admin"), now()))
    # sample "new products" on first run only (delete them from /admin/media)
    if os.environ.get("SEED_SAMPLES", "1") != "0" and not con.execute("SELECT 1 FROM new_products").fetchone():
        base = datetime.now(timezone.utc)
        for i, n in enumerate(reversed(CATALOG["new"])):
            ts = (base - timedelta(days=(len(CATALOG["new"]) - i) * 30)).strftime("%Y-%m-%d %H:%M:%S")
            con.execute("INSERT INTO new_products(name,category,description,art,created_at) VALUES(?,?,?,?,?)",
                        (n["name"], n["cat"], n["desc"], n["art"], ts))
    con.commit()
    con.close()


init_db()

# ------------------------------------------------------------------ security
@app.before_request
def load_user_and_check_csrf():
    g.user = None
    uid = session.get("uid")
    if uid:
        g.user = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Your session expired. Please go back, refresh the page and try again.")


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "form-action 'self'; base-uri 'self'")
    return resp


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(ok=False, error="Please log in first."), 401
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*a, **kw):
        if not g.user["is_admin"]:
            abort(403)
        return fn(*a, **kw)
    return wrapper


def safe_next(target):
    if not target:
        return None
    p = urlparse(target)
    if p.scheme or p.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


FAILS = {}


def throttled(key):
    t = time.time()
    FAILS[key] = [x for x in FAILS.get(key, []) if t - x < 600]
    return len(FAILS[key]) >= 5


# ------------------------------------------------------------------- helpers
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def norm_phone(p):
    d = re.sub(r"[^\d+]", "", p or "")
    if d.startswith("+"):
        d = d[1:]
    elif d.startswith("0") and len(d) == 10:
        d = "254" + d[1:]
    return d


def valid_phone(d):
    return d.isdigit() and 9 <= len(d) <= 15


def clean(s, n):
    return (s or "").strip()[:n]


def sniff_ext(data):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def save_image(file):
    """Save an uploaded photo (jpg/png/webp, max 5 MB). Returns filename or None."""
    if not file or not file.filename:
        return None
    data = file.read()
    ext = sniff_ext(data)
    if not ext or len(data) > 5 * 1024 * 1024:
        raise ValueError("Please upload a JPG, PNG or WEBP photo under 5 MB.")
    name = uuid.uuid4().hex + ext
    with open(os.path.join(UPLOAD_DIR, name), "wb") as fh:
        fh.write(data)
    return name


def new_product_dicts():
    rows = db().execute("SELECT * FROM new_products ORDER BY created_at DESC, id DESC").fetchall()
    out = []
    for r in rows:
        cat = next((c for c in CATS if c["name"] == r["category"]), None)
        out.append({"id": f"new/{r['id']}", "name": r["name"], "desc": r["description"], "cat": r["category"],
                    "art": r["art"] or (cat["art"] if cat else "tent"), "seed": CAT_INDEX.get(cat["id"], 2) if cat else 2,
                    "img": r["image"], "date": eat(r["created_at"], "%B %Y")})
    return out


def lookup_product(pid):
    if pid in PRODUCTS:
        return PRODUCTS[pid]
    if pid.startswith("new/") and pid[4:].isdigit():
        r = db().execute("SELECT * FROM new_products WHERE id=?", (int(pid[4:]),)).fetchone()
        if r:
            return {"id": pid, "name": r["name"], "cat": "New products"}
    return None


def eat(ts, fmt="%d %b %Y, %H:%M"):
    """UTC timestamp string -> East Africa Time text."""
    try:
        return (datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") + timedelta(hours=3)).strftime(fmt)
    except (TypeError, ValueError):
        return ts or ""


app.jinja_env.filters["eat"] = eat
app.jinja_env.globals.update(csrf_token=csrf_token, site=SITE, statuses=STATUSES, now_year=datetime.now().year)


@app.context_processor
def inject():
    return {"user": g.get("user"), "status_label": STATUS_LABEL}


# --------------------------------------------------------------- public pages
@app.route("/")
def home():
    return render_template("home.html", cats=CATS, latest=new_product_dicts()[:3], idx=CAT_INDEX)


@app.route("/products")
def products():
    return render_template("products.html", cats=CATS, idx=CAT_INDEX)


@app.route("/products/<cat_id>")
def category(cat_id):
    c = CAT_BY_ID.get(cat_id) or abort(404)
    items = [PRODUCTS[f'{c["id"]}/{it["id"]}'] for it in c["items"]]
    return render_template("category.html", c=c, items=items)


@app.route("/gallery")
def gallery():
    photos = db().execute("SELECT * FROM gallery ORDER BY created_at DESC, id DESC").fetchall()
    tiles = []
    for p in photos:
        c = CAT_BY_ID.get(p["cat_id"])
        tiles.append({"id": None, "name": p["title"], "cat": c["name"] if c else "", "cat_id": p["cat_id"],
                      "art": "tent", "seed": 0, "img": p["image"], "desc": ""})
    tiles += list(PRODUCTS.values())
    return render_template("gallery.html", tiles=tiles, cats=CATS)


@app.route("/new")
def new_page():
    return render_template("new.html", items=new_product_dicts())


@app.route("/blog")
def blog():
    return render_template("blog.html", posts=POSTS)


@app.route("/blog/<pid>")
def post(pid):
    p = next((x for x in POSTS if x["id"] == pid), None) or abort(404)
    return render_template("post.html", p=p)


@app.route("/jobs")
def jobs():
    return render_template("jobs.html", jobs=JOBS)


@app.post("/jobs/apply")
def jobs_apply():
    if request.form.get("website"):  # honeypot
        return redirect(url_for("jobs"))
    name, phone = clean(request.form.get("name"), 120), norm_phone(request.form.get("phone"))
    if not name or not valid_phone(phone):
        flash("Please enter your name and a valid phone number.", "error")
        return redirect(url_for("jobs") + "#apply")
    db().execute("INSERT INTO applications(name,phone,email,role,body,created_at) VALUES(?,?,?,?,?,?)",
                 (name, phone, clean(request.form.get("email"), 160), clean(request.form.get("role"), 160) or "General",
                  clean(request.form.get("msg"), 2000), now()))
    db().commit()
    flash("Thank you! Your application has been received. We will contact you if you are shortlisted.", "ok")
    return redirect(url_for("jobs"))


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        if request.form.get("website"):  # honeypot
            return redirect(url_for("contact"))
        name, phone = clean(request.form.get("name"), 120), norm_phone(request.form.get("phone"))
        body = clean(request.form.get("msg"), 3000)
        if not name or not valid_phone(phone) or not body:
            flash("Please fill in your name, a valid phone number and your message.", "error")
            return render_template("contact.html", form=request.form)
        db().execute("INSERT INTO messages(user_id,name,phone,body,created_at) VALUES(?,?,?,?,?)",
                     (g.user["id"] if g.user else None, name, phone, body, now()))
        db().commit()
        flash("Thank you! We have received your message and will get back to you soon.", "ok")
        return redirect(url_for("contact"))
    return render_template("contact.html", form={})


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/uploads/<name>")
def uploads(name):
    return send_from_directory(UPLOAD_DIR, name)


# ------------------------------------------------------------------ accounts
@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("account"))
    form = request.form
    if request.method == "POST":
        name, email = clean(form.get("name"), 120), clean(form.get("email"), 160).lower()
        phone, pw, pw2 = norm_phone(form.get("phone")), form.get("password", ""), form.get("password2", "")
        code = clean(form.get("ref"), 20).upper()
        errors = []
        if len(name) < 2:
            errors.append("Please enter your full name.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")
        if not valid_phone(phone):
            errors.append("Please enter a valid phone number, e.g. 0712 345 678.")
        if len(pw) < 8:
            errors.append("Your password must be at least 8 characters.")
        if pw != pw2:
            errors.append("The two passwords do not match.")
        if not form.get("consent"):
            errors.append("Please agree to the privacy notice to create an account.")
        referrer = None
        if code:
            referrer = db().execute("SELECT id FROM users WHERE ref_code=?", (code,)).fetchone()
            if not referrer:
                errors.append("That referral code was not recognised. Leave it blank if you do not have one.")
        if not errors and db().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            errors.append("An account with that email already exists. Please log in instead.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", form=form)
        cur = db().execute(
            "INSERT INTO users(name,email,phone,pw_hash,ref_code,referred_by,consent_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (name, email, phone, generate_password_hash(pw), make_ref_code(db(), name),
             referrer["id"] if referrer else None, now(), now()))
        db().commit()
        session.clear()
        session["uid"] = cur.lastrowid
        session.permanent = True
        flash("Welcome! Your account is ready.", "ok")
        return redirect(safe_next(request.args.get("next")) or url_for("account"))
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("account"))
    if request.method == "POST":
        email = clean(request.form.get("email"), 160).lower()
        key = f"{request.remote_addr}|{email}"
        if throttled(key):
            flash("Too many attempts. Please wait a few minutes and try again.", "error")
            return render_template("login.html")
        u = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and check_password_hash(u["pw_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"] = u["id"]
            session.permanent = True
            return redirect(safe_next(request.args.get("next")) or (url_for("admin") if u["is_admin"] else url_for("account")))
        FAILS.setdefault(key, []).append(time.time())
        flash("Incorrect email or password.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "ok")
    return redirect(url_for("home"))


@app.route("/account")
@login_required
def account():
    orders = db().execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
    items = {}
    for it in db().execute("SELECT * FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id=?)", (g.user["id"],)):
        items.setdefault(it["order_id"], []).append(it)
    ref = db().execute(
        "SELECT COUNT(*) n, SUM(status='delivered_paid') d FROM orders WHERE referrer_id=?", (g.user["id"],)).fetchone()
    return render_template("account.html", orders=orders, items=items, ref=ref, placed=request.args.get("placed"))


@app.post("/account/password")
@login_required
def change_password():
    if not check_password_hash(g.user["pw_hash"], request.form.get("current", "")):
        flash("Your current password is not correct.", "error")
    elif len(request.form.get("new", "")) < 8:
        flash("Your new password must be at least 8 characters.", "error")
    else:
        db().execute("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(request.form["new"]), g.user["id"]))
        db().commit()
        flash("Password updated.", "ok")
    return redirect(url_for("account"))


# -------------------------------------------------------------------- orders
@app.route("/order")
@login_required
def order_page():
    return render_template("order.html")


@app.post("/api/order")
@login_required
def api_order():
    d = request.get_json(silent=True) or {}

    def fail(msg):
        return jsonify(ok=False, error=msg), 400

    location = clean(d.get("location"), 200)
    extra = clean(d.get("extra"), 1500)
    if not location:
        return fail("Please enter a delivery location.")
    raw = d.get("items") or []
    if not isinstance(raw, list) or len(raw) > 40:
        return fail("Your order has too many items.")
    lines = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        p = lookup_product(str(it.get("id", "")))
        if not p:
            continue
        try:
            qty = max(1, min(int(it.get("qty", 1)), 1000))
        except (TypeError, ValueError):
            qty = 1
        lines.append((p["id"], p["name"], p["cat"], qty, clean(str(it.get("note", "")), 200)))
    if not lines and not extra:
        return fail("Please add at least one product, or describe what you need.")
    delivery = None
    if d.get("date"):
        try:
            delivery = date.fromisoformat(str(d["date"])).isoformat()
        except ValueError:
            return fail("That delivery date is not valid.")
    referrer_id = None
    code = clean(d.get("ref"), 20).upper()
    if code:
        r = db().execute("SELECT id FROM users WHERE ref_code=?", (code,)).fetchone()
        if not r or r["id"] == g.user["id"]:
            return fail("That referral code was not recognised.")
        referrer_id = r["id"]
    elif g.user["referred_by"]:
        referrer_id = g.user["referred_by"]

    while True:
        ref = f"ORD-{datetime.now(timezone.utc):%y%m%d}-{secrets.randbelow(9000) + 1000}"
        if not db().execute("SELECT 1 FROM orders WHERE ref=?", (ref,)).fetchone():
            break
    cur = db().execute(
        "INSERT INTO orders(ref,user_id,name,phone,location,delivery_date,extra,referrer_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (ref, g.user["id"], g.user["name"], g.user["phone"], location, delivery, extra, referrer_id, now()))
    for pid, name, cat, qty, note in lines:
        db().execute("INSERT INTO order_items(order_id,product_id,name,category,qty,note) VALUES(?,?,?,?,?,?)",
                     (cur.lastrowid, pid, name, cat, qty, note))
    db().commit()
    return jsonify(ok=True, ref=ref)


# --------------------------------------------------------------------- admin
@app.route("/admin")
@admin_required
def admin():
    status = request.args.get("status", "")
    q = "SELECT o.*, (SELECT COUNT(*) FROM order_items i WHERE i.order_id=o.id) n FROM orders o"
    args = ()
    if status in STATUS_LABEL:
        q += " WHERE status=?"
        args = (status,)
    orders = db().execute(q + " ORDER BY created_at DESC LIMIT 300", args).fetchall()
    counts = {r["status"]: r["n"] for r in db().execute("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
    stats = {
        "customers": db().execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
        "messages": db().execute("SELECT COUNT(*) FROM messages WHERE handled=0").fetchone()[0],
        "applications": db().execute("SELECT COUNT(*) FROM applications WHERE handled=0").fetchone()[0],
    }
    return render_template("admin_orders.html", orders=orders, counts=counts, stats=stats, current=status)


@app.route("/admin/orders/<int:oid>")
@admin_required
def admin_order(oid):
    o = db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone() or abort(404)
    items = db().execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()
    customer = db().execute("SELECT * FROM users WHERE id=?", (o["user_id"],)).fetchone()
    referrer = db().execute("SELECT * FROM users WHERE id=?", (o["referrer_id"],)).fetchone() if o["referrer_id"] else None
    return render_template("admin_order.html", o=o, items=items, customer=customer, referrer=referrer)


@app.post("/admin/orders/<int:oid>")
@admin_required
def admin_order_update(oid):
    status = request.form.get("status")
    if status not in STATUS_LABEL:
        abort(400)
    db().execute("UPDATE orders SET status=?, admin_note=?, commission_paid=? WHERE id=?",
                 (status, clean(request.form.get("admin_note"), 1000), 1 if request.form.get("commission_paid") else 0, oid))
    db().commit()
    flash("Order updated.", "ok")
    return redirect(url_for("admin_order", oid=oid))


@app.route("/admin/customers")
@admin_required
def admin_customers():
    rows = db().execute(
        "SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id) orders, "
        "(SELECT name FROM users r WHERE r.id=u.referred_by) referrer FROM users u WHERE is_admin=0 ORDER BY created_at DESC").fetchall()
    return render_template("admin_customers.html", rows=rows)


@app.post("/admin/customers/<int:uid>/reset-password")
@admin_required
def admin_reset_password(uid):
    u = db().execute("SELECT * FROM users WHERE id=? AND is_admin=0", (uid,)).fetchone() or abort(404)
    temp = secrets.token_urlsafe(8)
    db().execute("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(temp), uid))
    db().commit()
    flash(f"Temporary password for {u['name']}: {temp}  — send it to them and ask them to change it after logging in.", "ok")
    return redirect(url_for("admin_customers"))


@app.route("/admin/inbox")
@admin_required
def admin_inbox():
    msgs = db().execute("SELECT * FROM messages ORDER BY handled, created_at DESC LIMIT 200").fetchall()
    apps_ = db().execute("SELECT * FROM applications ORDER BY handled, created_at DESC LIMIT 200").fetchall()
    return render_template("admin_inbox.html", msgs=msgs, apps=apps_)


@app.post("/admin/inbox/<kind>/<int:rid>/done")
@admin_required
def admin_inbox_done(kind, rid):
    if kind not in ("messages", "applications"):
        abort(404)
    db().execute(f"UPDATE {kind} SET handled=1 WHERE id=?", (rid,))
    db().commit()
    return redirect(url_for("admin_inbox"))


@app.route("/admin/referrals")
@admin_required
def admin_referrals():
    rows = db().execute(
        "SELECT r.id, r.name, r.phone, r.ref_code, COUNT(o.id) orders, "
        "SUM(o.status='delivered_paid') delivered, SUM(o.status='delivered_paid' AND o.commission_paid=1) paid "
        "FROM users r JOIN orders o ON o.referrer_id=r.id GROUP BY r.id ORDER BY delivered DESC, orders DESC").fetchall()
    return render_template("admin_referrals.html", rows=rows)


@app.route("/admin/media", methods=["GET", "POST"])
@admin_required
def admin_media():
    if request.method == "POST":
        kind = request.form.get("kind")
        try:
            img = save_image(request.files.get("image"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_media"))
        if kind == "product":
            cat = CAT_BY_ID.get(request.form.get("cat_id"))
            name, desc = clean(request.form.get("name"), 160), clean(request.form.get("desc"), 1000)
            if not (cat and name and desc):
                flash("Please fill in the name, category and description.", "error")
            else:
                db().execute("INSERT INTO new_products(name,category,description,art,image,created_at) VALUES(?,?,?,?,?,?)",
                             (name, cat["name"], desc, cat["art"], img, now()))
                db().commit()
                flash("New product posted.", "ok")
        elif kind == "gallery":
            title, cat = clean(request.form.get("title"), 160), CAT_BY_ID.get(request.form.get("cat_id"))
            if not (img and title and cat):
                flash("A gallery photo needs a photo, a title and a category.", "error")
            else:
                db().execute("INSERT INTO gallery(title,cat_id,image,created_at) VALUES(?,?,?,?)", (title, cat["id"], img, now()))
                db().commit()
                flash("Photo added to the gallery.", "ok")
        return redirect(url_for("admin_media"))
    new = db().execute("SELECT * FROM new_products ORDER BY created_at DESC").fetchall()
    gal = db().execute("SELECT * FROM gallery ORDER BY created_at DESC").fetchall()
    return render_template("admin_media.html", new=new, gal=gal, cats=CATS)


@app.post("/admin/media/delete/<kind>/<int:rid>")
@admin_required
def admin_media_delete(kind, rid):
    table = {"product": "new_products", "gallery": "gallery"}.get(kind) or abort(404)
    row = db().execute(f"SELECT image FROM {table} WHERE id=?", (rid,)).fetchone()
    if row and row["image"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row["image"]))
        except OSError:
            pass
    db().execute(f"DELETE FROM {table} WHERE id=?", (rid,))
    db().commit()
    flash("Deleted.", "ok")
    return redirect(url_for("admin_media"))


def csv_safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@app.route("/admin/export/orders.csv")
@admin_required
def admin_export():
    rows = db().execute(
        "SELECT o.ref, o.created_at, o.status, o.name, o.phone, u.email, o.location, o.delivery_date, "
        "r.name referrer, o.commission_paid, o.extra, "
        "(SELECT group_concat(i.name || ' x' || i.qty || CASE WHEN i.note<>'' THEN ' (' || i.note || ')' ELSE '' END, '; ') "
        " FROM order_items i WHERE i.order_id=o.id) items "
        "FROM orders o JOIN users u ON u.id=o.user_id LEFT JOIN users r ON r.id=o.referrer_id ORDER BY o.created_at DESC").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Order", "Placed (EAT)", "Status", "Name", "Phone", "Email", "Location", "Delivery date",
                "Referred by", "Commission paid", "Extra details", "Items"])
    for r in rows:
        w.writerow([csv_safe(r["ref"]), eat(r["created_at"]), STATUS_LABEL.get(r["status"], r["status"]), csv_safe(r["name"]),
                    csv_safe(r["phone"]), csv_safe(r["email"]), csv_safe(r["location"]), r["delivery_date"] or "",
                    csv_safe(r["referrer"]), "yes" if r["commission_paid"] else "no", csv_safe(r["extra"]), csv_safe(r["items"])])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=orders.csv"})


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def error_page(e):
    return render_template("error.html", e=e), e.code


if __name__ == "__main__":
    app.run(debug=os.environ.get("DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
