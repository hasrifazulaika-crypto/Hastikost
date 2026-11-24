import os
import sqlite3
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "kos-manager-dev-secret-change-in-prod")
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
DB_PATH = os.path.join(DB_DIR, "kos_manager.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'tenant')),
        full_name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT UNIQUE NOT NULL,
        room_type TEXT NOT NULL,
        monthly_price INTEGER NOT NULL,
        facilities TEXT,
        status TEXT NOT NULL DEFAULT 'tersedia' CHECK(status IN ('tersedia', 'terisi', 'perbaikan'))
    );

    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        room_id INTEGER,
        full_name TEXT NOT NULL,
        whatsapp TEXT NOT NULL,
        email TEXT,
        address TEXT,
        id_number TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT,
        monthly_rate INTEGER NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (room_id) REFERENCES rooms(id)
    );

    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        period_month TEXT NOT NULL,
        amount INTEGER NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'BELUM BAYAR' CHECK(status IN ('BELUM BAYAR', 'MENUNGGU VERIFIKASI', 'LUNAS')),
        paid_at TEXT,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        method TEXT NOT NULL,
        amount INTEGER NOT NULL,
        proof_file TEXT,
        note TEXT,
        verified_by INTEGER,
        verified_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (invoice_id) REFERENCES invoices(id),
        FOREIGN KEY (verified_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        amount INTEGER NOT NULL,
        expense_date TEXT NOT NULL,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'BARU',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('kos_name', 'KOS MANAGER - Smart Boarding House')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bank_info', 'BCA 1234567890 a.n. Pemilik Kos')")

    admin_exists = cur.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not admin_exists:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'admin', ?)",
            ("admin", generate_password_hash("admin123"), "Admin Kos Manager"),
        )

    tenant_user = cur.execute("SELECT id FROM users WHERE username = 'penghuni1'").fetchone()
    if not tenant_user:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'tenant', ?)",
            ("penghuni1", generate_password_hash("kos123"), "Rina Putri"),
        )
        t_uid = cur.lastrowid

        cur.execute(
            "INSERT OR IGNORE INTO rooms (room_number, room_type, monthly_price, facilities, status) VALUES (?, ?, ?, ?, 'terisi')",
            ("A-01", "AC + Kamar Mandi Dalam", 1200000, "AC, Kasur, Lemari, Wi-Fi, KM Dalam"),
        )
        cur.execute(
            "INSERT OR IGNORE INTO rooms (room_number, room_type, monthly_price, facilities, status) VALUES (?, ?, ?, ?, 'tersedia')",
            ("A-02", "Kipas + Kamar Mandi Luar", 850000, "Kasur, Meja, Lemari, Wi-Fi"),
        )
        room = cur.execute("SELECT id FROM rooms WHERE room_number = 'A-01'").fetchone()
        cur.execute(
            """INSERT INTO tenants (user_id, room_id, full_name, whatsapp, email, start_date, monthly_rate, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (t_uid, room["id"], "Rina Putri", "6281234567890", "rina@example.com", datetime.now().strftime("%Y-%m-01"), 1200000),
        )
        tenant_row = cur.execute("SELECT id FROM tenants WHERE user_id = ?", (t_uid,)).fetchone()
        period_now = datetime.now().strftime("%Y-%m")
        cur.execute(
            "INSERT INTO invoices (tenant_id, period_month, amount, due_date, status) VALUES (?, ?, ?, ?, 'BELUM BAYAR')",
            (tenant_row["id"], period_now, 1200000, f"{period_now}-10"),
        )

    conn.commit()
    conn.close()


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Akses ditolak untuk peran akun ini.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def format_rp(val):
    return f"Rp {int(val or 0):,}".replace(",", ".")


app.jinja_env.filters["rp"] = format_rp


BASE_HTML = """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KOS MANAGER</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
  <div class="container">
    <a class="navbar-brand fw-bold" href="{{ url_for('dashboard') }}">KOS MANAGER</a>
    {% if session.get('user_id') %}
    <div class="d-flex align-items-center gap-2">
      <span class="text-light small">{{ session.get('full_name') }} ({{ session.get('role') }})</span>
      <a class="btn btn-outline-light btn-sm" href="{{ url_for('logout') }}">Keluar</a>
    </div>
    {% endif %}
  </div>
</nav>
<div class="container pb-5">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  {{ content|safe }}
</div>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("dashboard"))
        flash("Username atau password salah.", "danger")

    form_html = """
    <div class="row justify-content-center">
      <div class="col-md-4">
        <div class="card shadow-sm">
          <div class="card-body">
            <h4 class="mb-3">Masuk KOS MANAGER</h4>
            <form method="post">
              <div class="mb-3">
                <label class="form-label">Username</label>
                <input type="text" name="username" class="form-control" required>
              </div>
              <div class="mb-3">
                <label class="form-label">Password</label>
                <input type="password" name="password" class="form-control" required>
              </div>
              <button class="btn btn-primary w-100">Masuk</button>
            </form>
            <hr>
            <small class="text-muted d-block">Admin: <b>admin</b> / <b>admin123</b></small>
            <small class="text-muted d-block">Penghuni: <b>penghuni1</b> / <b>kos123</b></small>
          </div>
        </div>
      </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=form_html)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required()
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("tenant_portal"))


@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    conn = get_db()
    total_rooms = conn.execute("SELECT COUNT(*) AS c FROM rooms").fetchone()["c"]
    occupied_rooms = conn.execute("SELECT COUNT(*) AS c FROM rooms WHERE status='terisi'").fetchone()["c"]
    available_rooms = conn.execute("SELECT COUNT(*) AS c FROM rooms WHERE status='tersedia'").fetchone()["c"]
    active_tenants = conn.execute("SELECT COUNT(*) AS c FROM tenants WHERE is_active=1").fetchone()["c"]

    income = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM invoices WHERE status='LUNAS'").fetchone()["s"]
    receivable = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM invoices WHERE status!='LUNAS'").fetchone()["s"]
    expense = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM expenses").fetchone()["s"]
    net_profit = income - expense

    rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
    avail_rooms = conn.execute("SELECT * FROM rooms WHERE status='tersedia' ORDER BY room_number").fetchall()
    tenants = conn.execute("""
        SELECT t.*, r.room_number, u.username
        FROM tenants t
        LEFT JOIN rooms r ON t.room_id = r.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.is_active = 1
    """).fetchall()
    invoices = conn.execute("""
        SELECT i.*, t.full_name, t.whatsapp, r.room_number
        FROM invoices i
        JOIN tenants t ON i.tenant_id = t.id
        LEFT JOIN rooms r ON t.room_id = r.id
        ORDER BY i.id DESC
    """).fetchall()
    expenses = conn.execute("SELECT * FROM expenses ORDER BY expense_date DESC").fetchall()
    complaints = conn.execute("""
        SELECT c.*, t.full_name, r.room_number
        FROM complaints c
        JOIN tenants t ON c.tenant_id = t.id
        LEFT JOIN rooms r ON t.room_id = r.id
        ORDER BY c.id DESC
    """).fetchall()
    conn.close()

    inv_rows = ""
    for inv in invoices:
        wa_text = quote(
            f"Halo {inv['full_name']}, tagihan kos kamar {inv['room_number'] or '-'} "
            f"periode {inv['period_month']} sebesar {format_rp(inv['amount'])} "
            f"(Jatuh tempo: {inv['due_date']}). Status: {inv['status']}."
        )
        wa_link = f"https://wa.me/{inv['whatsapp']}?text={wa_text}"
        action_btn = ""
        if inv["status"] != "LUNAS":
            action_btn = f"""
            <form method="post" action="/admin/invoices/{inv['id']}/verify" class="d-inline">
              <button class="btn btn-success btn-sm">Tandai LUNAS</button>
            </form>
            """
        inv_rows += f"""
        <tr>
          <td>{inv['full_name']} ({inv['room_number'] or '-'})</td>
          <td>{inv['period_month']}</td>
          <td>{format_rp(inv['amount'])}</td>
          <td><span class="badge bg-secondary">{inv['status']}</span></td>
          <td>
            <a href="{wa_link}" target="_blank" class="btn btn-outline-success btn-sm">Kirim WA</a>
            {action_btn}
          </td>
        </tr>
        """

    room_rows = "".join(
        f"<tr><td>{r['room_number']}</td><td>{r['room_type']}</td><td>{format_rp(r['monthly_price'])}</td><td>{r['status']}</td></tr>"
        for r in rooms
    )
    tenant_rows = "".join(
        f"<tr><td>{t['full_name']}</td><td>{t['username'] or '-'}</td><td>{t['room_number'] or '-'}</td><td>{t['whatsapp']}</td><td>{format_rp(t['monthly_rate'])}</td></tr>"
        for t in tenants
    )
    exp_rows = "".join(
        f"<tr><td>{e['expense_date']}</td><td>{e['category']}</td><td>{format_rp(e['amount'])}</td><td>{e['description'] or '-'}</td></tr>"
        for e in expenses
    )
    comp_rows = "".join(
        f"<tr><td>{c['full_name']} ({c['room_number'] or '-'})</td><td><b>{c['title']}</b>: {c['description']}</td><td><span class='badge bg-warning text-dark'>{c['status']}</span></td></tr>"
        for c in complaints
    )
    tenant_opts = "".join(f"<option value='{t['id']}'>{t['full_name']} ({format_rp(t['monthly_rate'])})</option>" for t in tenants)
    avail_room_opts = "".join(f"<option value='{r['id']}'>{r['room_number']} - {r['room_type']} ({format_rp(r['monthly_price'])})</option>" for r in avail_rooms)

    body = f"""
    <h3 class="mb-3">Dashboard Admin</h3>
    <div class="row g-3 mb-4">
      <div class="col-md-3"><div class="card p-3"><small class="text-muted">Kamar Terisi / Total</small><h4>{occupied_rooms} / {total_rooms}</h4><small>Kosong: {available_rooms} | Penghuni: {active_tenants}</small></div></div>
      <div class="col-md-3"><div class="card p-3"><small class="text-muted">Pendapatan (Lunas)</small><h4 class="text-success">{format_rp(income)}</h4></div></div>
      <div class="col-md-3"><div class="card p-3"><small class="text-muted">Piutang</small><h4 class="text-warning">{format_rp(receivable)}</h4></div></div>
      <div class="col-md-3"><div class="card p-3"><small class="text-muted">Laba Bersih</small><h4>{format_rp(net_profit)}</h4><small class="text-muted">Pengeluaran: {format_rp(expense)}</small></div></div>
    </div>

    <div class="row g-4 mb-4">
      <div class="col-md-4">
        <div class="card p-3 h-100">
          <h5>Tambah Kamar</h5>
          <form method="post" action="/admin/rooms" class="row g-2">
            <div class="col-6"><input name="room_number" class="form-control form-control-sm" placeholder="No. Kamar (A-03)" required></div>
            <div class="col-6"><input name="room_type" class="form-control form-control-sm" placeholder="Tipe Kamar" required></div>
            <div class="col-6"><input name="monthly_price" type="number" class="form-control form-control-sm" placeholder="Harga/bulan" required></div>
            <div class="col-6"><input name="facilities" class="form-control form-control-sm" placeholder="Fasilitas"></div>
            <div class="col-12"><button class="btn btn-primary btn-sm">Simpan Kamar</button></div>
          </form>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card p-3 h-100">
          <h5>Tambah Penghuni & Akun</h5>
          <form method="post" action="/admin/tenants" class="row g-2">
            <div class="col-6"><input name="full_name" class="form-control form-control-sm" placeholder="Nama Lengkap" required></div>
            <div class="col-6"><input name="whatsapp" class="form-control form-control-sm" placeholder="WA (628xxx)" required></div>
            <div class="col-6"><input name="username" class="form-control form-control-sm" placeholder="Username Login" required></div>
            <div class="col-6"><input name="password" class="form-control form-control-sm" placeholder="Password" required></div>
            <div class="col-12"><select name="room_id" class="form-select form-select-sm" required><option value="">-- Pilih Kamar Kosong --</option>{avail_room_opts}</select></div>
            <div class="col-12"><button class="btn btn-primary btn-sm">Simpan Penghuni</button></div>
          </form>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card p-3 h-100">
          <h5>Buat Tagihan Bulanan</h5>
          <form method="post" action="/admin/invoices" class="row g-2">
            <div class="col-12"><select name="tenant_id" class="form-select form-select-sm" required>{tenant_opts}</select></div>
            <div class="col-12"><input name="period_month" class="form-control form-control-sm" value="{datetime.now().strftime('%Y-%m')}" required></div>
            <div class="col-12"><button class="btn btn-success btn-sm">Generate Tagihan</button></div>
          </form>
        </div>
      </div>
    </div>

    <div class="card p-3 mb-4">
      <h5>Daftar Tagihan & WhatsApp</h5>
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead><tr><th>Penghuni</th><th>Periode</th><th>Nominal</th><th>Status</th><th>Aksi</th></tr></thead>
          <tbody>{inv_rows or '<tr><td colspan="5">Belum ada tagihan.</td></tr>'}</tbody>
        </table>
      </div>
    </div>

    <div class="row g-4 mb-4">
      <div class="col-md-6">
        <div class="card p-3">
          <h5>Daftar Kamar</h5>
          <table class="table table-sm"><thead><tr><th>No</th><th>Tipe</th><th>Tarif</th><th>Status</th></tr></thead><tbody>{room_rows}</tbody></table>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card p-3">
          <h5>Daftar Penghuni Aktif</h5>
          <table class="table table-sm"><thead><tr><th>Nama</th><th>User</th><th>Kamar</th><th>WA</th><th>Tarif</th></tr></thead><tbody>{tenant_rows}</tbody></table>
        </div>
      </div>
    </div>

    <div class="row g-4">
      <div class="col-md-6">
        <div class="card p-3">
          <h5>Catat Pengeluaran</h5>
          <form method="post" action="/admin/expenses" class="row g-2 mb-3">
            <div class="col-md-4"><input name="category" class="form-control form-control-sm" placeholder="Kategori (Listrik/Air)" required></div>
            <div class="col-md-3"><input name="amount" type="number" class="form-control form-control-sm" placeholder="Nominal" required></div>
            <div class="col-md-3"><input name="description" class="form-control form-control-sm" placeholder="Keterangan"></div>
            <div class="col-md-2"><button class="btn btn-dark btn-sm w-100">Catat</button></div>
          </form>
          <table class="table table-sm"><thead><tr><th>Tanggal</th><th>Kategori</th><th>Nominal</th><th>Ket</th></tr></thead><tbody>{exp_rows}</tbody></table>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card p-3">
          <h5>Keluhan Penghuni</h5>
          <table class="table table-sm"><thead><tr><th>Penghuni</th><th>Keluhan</th><th>Status</th></tr></thead><tbody>{comp_rows or '<tr><td colspan="3">Belum ada keluhan.</td></tr>'}</tbody></table>
        </div>
      </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=body)


@app.route("/admin/rooms", methods=["POST"])
@login_required("admin")
def add_room():
    conn = get_db()
    conn.execute(
        "INSERT INTO rooms (room_number, room_type, monthly_price, facilities, status) VALUES (?, ?, ?, ?, 'tersedia')",
        (
            request.form["room_number"].strip(),
            request.form["room_type"].strip(),
            int(request.form["monthly_price"]),
            request.form.get("facilities", "").strip(),
        ),
    )
    conn.commit()
    conn.close()
    flash("Kamar berhasil ditambahkan.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/tenants", methods=["POST"])
@login_required("admin")
def add_tenant():
    full_name = request.form["full_name"].strip()
    whatsapp = request.form["whatsapp"].strip()
    username = request.form["username"].strip()
    password = request.form["password"]
    room_id = int(request.form["room_id"])

    conn = get_db()
    room = conn.execute("SELECT monthly_price FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'tenant', ?)",
            (username, generate_password_hash(password), full_name),
        )
        user_id = cur.lastrowid
        cur.execute(
            """INSERT INTO tenants (user_id, room_id, full_name, whatsapp, start_date, monthly_rate, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (user_id, room_id, full_name, whatsapp, datetime.now().strftime("%Y-%m-%d"), room["monthly_price"]),
        )
        cur.execute("UPDATE rooms SET status = 'terisi' WHERE id = ?", (room_id,))
        conn.commit()
        flash("Penghuni dan akun login berhasil dibuat.", "success")
    conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/invoices", methods=["POST"])
@login_required("admin")
def create_invoice():
    tenant_id = int(request.form["tenant_id"])
    period_month = request.form["period_month"].strip()
    conn = get_db()
    tenant = conn.execute("SELECT monthly_rate FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    if tenant:
        conn.execute(
            "INSERT INTO invoices (tenant_id, period_month, amount, due_date, status) VALUES (?, ?, ?, ?, 'BELUM BAYAR')",
            (tenant_id, period_month, tenant["monthly_rate"], f"{period_month}-10"),
        )
        conn.commit()
        flash("Tagihan berhasil dibuat.", "success")
    conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/invoices/<int:invoice_id>/verify", methods=["POST"])
@login_required("admin")
def verify_invoice(invoice_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "UPDATE invoices SET status = 'LUNAS', paid_at = ? WHERE id = ?",
        (now_str, invoice_id),
    )
    conn.execute(
        "UPDATE payments SET verified_by = ?, verified_at = ? WHERE invoice_id = ?",
        (session["user_id"], now_str, invoice_id),
    )
    conn.commit()
    conn.close()
    flash("Pembayaran diverifikasi dan status diubah menjadi LUNAS.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/expenses", methods=["POST"])
@login_required("admin")
def add_expense():
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (category, amount, expense_date, description) VALUES (?, ?, ?, ?)",
        (
            request.form["category"].strip(),
            int(request.form["amount"]),
            datetime.now().strftime("%Y-%m-%d"),
            request.form.get("description", "").strip(),
        ),
    )
    conn.commit()
    conn.close()
    flash("Pengeluaran berhasil dicatat.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/tenant")
@login_required("tenant")
def tenant_portal():
    conn = get_db()
    tenant = conn.execute("""
        SELECT t.*, r.room_number, r.room_type, r.facilities
        FROM tenants t LEFT JOIN rooms r ON t.room_id = r.id
        WHERE t.user_id = ?
    """, (session["user_id"],)).fetchone()

    invoices = []
    complaints = []
    if tenant:
        invoices = conn.execute(
            "SELECT * FROM invoices WHERE tenant_id = ? ORDER BY id DESC",
            (tenant["id"],),
        ).fetchall()
        complaints = conn.execute(
            "SELECT * FROM complaints WHERE tenant_id = ? ORDER BY id DESC",
            (tenant["id"],),
        ).fetchall()
    conn.close()

    rows_html = ""
    for inv in invoices:
        pay_form = ""
        if inv["status"] == "BELUM BAYAR":
            pay_form = f"""
            <form method="post" action="/tenant/invoices/{inv['id']}/pay" enctype="multipart/form-data" class="d-flex gap-1">
              <select name="method" class="form-select form-select-sm" style="width:130px">
                <option value="Transfer Manual">Transfer Manual</option>
                <option value="QRIS">QRIS</option>
                <option value="Virtual Account">Virtual Account</option>
              </select>
              <input type="file" name="proof" class="form-control form-control-sm" style="width:180px">
              <button class="btn btn-primary btn-sm">Bayar</button>
            </form>
            """
        rows_html += f"""
        <tr>
          <td>{inv['period_month']}</td>
          <td>{format_rp(inv['amount'])}</td>
          <td>{inv['due_date']}</td>
          <td><span class="badge bg-info text-dark">{inv['status']}</span></td>
          <td>{pay_form or '-'}</td>
        </tr>
        """

    comp_rows = "".join(
        f"<tr><td>{c['created_at']}</td><td>{c['title']}</td><td>{c['description']}</td><td>{c['status']}</td></tr>"
        for c in complaints
    )

    body = f"""
    <h3>Portal Penghuni</h3>
    <div class="card p-3 mb-4">
      <b>{tenant['full_name'] if tenant else session['full_name']}</b> |
      Kamar: <b>{tenant['room_number'] if tenant and tenant['room_number'] else '-'}</b> ({tenant['room_type'] if tenant else '-'}) |
      Tarif: <b>{format_rp(tenant['monthly_rate']) if tenant else '-'}</b><br>
      <small class="text-muted">Fasilitas: {tenant['facilities'] if tenant and tenant['facilities'] else '-'}</small>
    </div>
    <div class="card p-3 mb-4">
      <h5>Daftar Tagihan Saya</h5>
      <table class="table table-sm align-middle">
        <thead><tr><th>Periode</th><th>Nominal</th><th>Jatuh Tempo</th><th>Status</th><th>Konfirmasi Pembayaran</th></tr></thead>
        <tbody>{rows_html or '<tr><td colspan="5">Tidak ada tagihan.</td></tr>'}</tbody>
      </table>
    </div>
    <div class="card p-3">
      <h5>Kirim Keluhan</h5>
      <form method="post" action="/tenant/complaints" class="row g-2 mb-3">
        <div class="col-md-4"><input name="title" class="form-control form-control-sm" placeholder="Judul keluhan (mis. AC kurang dingin)" required></div>
        <div class="col-md-6"><input name="description" class="form-control form-control-sm" placeholder="Detail keluhan" required></div>
        <div class="col-md-2"><button class="btn btn-warning btn-sm w-100">Kirim</button></div>
      </form>
      <table class="table table-sm"><thead><tr><th>Waktu</th><th>Judul</th><th>Detail</th><th>Status</th></tr></thead><tbody>{comp_rows}</tbody></table>
    </div>
    """
    return render_template_string(BASE_HTML, content=body)


@app.route("/tenant/invoices/<int:invoice_id>/pay", methods=["POST"])
@login_required("tenant")
def pay_invoice(invoice_id):
    method = request.form.get("method", "Transfer Manual")
    file = request.files.get("proof")
    filename = None
    if file and file.filename:
        filename = secure_filename(f"{invoice_id}_{file.filename}")
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    conn = get_db()
    inv = conn.execute("SELECT amount FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if inv:
        conn.execute(
            "INSERT INTO payments (invoice_id, method, amount, proof_file) VALUES (?, ?, ?, ?)",
            (invoice_id, method, inv["amount"], filename),
        )
        conn.execute(
            "UPDATE invoices SET status = 'MENUNGGU VERIFIKASI' WHERE id = ?",
            (invoice_id,),
        )
        conn.commit()
        flash("Bukti/konfirmasi pembayaran dikirim. Menunggu verifikasi admin.", "info")
    conn.close()
    return redirect(url_for("tenant_portal"))


@app.route("/tenant/complaints", methods=["POST"])
@login_required("tenant")
def add_complaint():
    conn = get_db()
    tenant = conn.execute("SELECT id FROM tenants WHERE user_id = ?", (session["user_id"],)).fetchone()
    if tenant:
        conn.execute(
            "INSERT INTO complaints (tenant_id, title, description) VALUES (?, ?, ?)",
            (tenant["id"], request.form["title"].strip(), request.form["description"].strip()),
        )
        conn.commit()
        flash("Keluhan berhasil dikirim ke admin.", "success")
    conn.close()
    return redirect(url_for("tenant_portal"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
