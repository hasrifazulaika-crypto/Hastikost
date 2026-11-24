import os
import sqlite3
import hashlib
from datetime import datetime
from urllib.parse import quote
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="KOS MANAGER - Smart Boarding House",
    page_icon="🏠",
    layout="wide",
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "kos_manager.db")


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def format_rp(val) -> str:
    return f"Rp {int(val or 0):,}".replace(",", ".")


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
            ("admin", hash_pw("admin123"), "Admin Kos Manager"),
        )

    tenant_user = cur.execute("SELECT id FROM users WHERE username = 'penghuni1'").fetchone()
    if not tenant_user:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'tenant', ?)",
            ("penghuni1", hash_pw("kos123"), "Rina Putri"),
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


init_db()

if "user" not in st.session_state:
    st.session_state.user = None


def login_view():
    st.title("🏠 KOS MANAGER")
    st.caption("Smart Boarding House Management & Financial System")
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Masuk ke Sistem")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Masuk", use_container_width=True)
            if submitted:
                conn = get_db()
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ? AND password_hash = ?",
                    (username.strip(), hash_pw(password)),
                ).fetchone()
                conn.close()
                if user:
                    st.session_state.user = dict(user)
                    st.rerun()
                else:
                    st.error("Username atau password salah.")
        st.info("Akun Demo — Admin: `admin` / `admin123` | Penghuni: `penghuni1` / `kos123`")


def admin_view():
    user = st.session_state.user
    with st.sidebar:
        st.title("🏠 KOS MANAGER")
        st.write(f"Halo, **{user['full_name']}**")
        menu = st.radio(
            "Menu Admin",
            [
                "Dashboard",
                "Manajemen Kamar",
                "Data Penghuni",
                "Tagihan & WhatsApp",
                "Pengeluaran & Laporan",
                "Keluhan Penghuni",
                "Pengaturan Kos",
            ],
        )
        if st.button("Keluar", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    conn = get_db()

    if menu == "Dashboard":
        st.header("📊 Dashboard Admin")
        total_rooms = conn.execute("SELECT COUNT(*) AS c FROM rooms").fetchone()["c"]
        occupied = conn.execute("SELECT COUNT(*) AS c FROM rooms WHERE status='terisi'").fetchone()["c"]
        available = conn.execute("SELECT COUNT(*) AS c FROM rooms WHERE status='tersedia'").fetchone()["c"]
        active_tenants = conn.execute("SELECT COUNT(*) AS c FROM tenants WHERE is_active=1").fetchone()["c"]

        income = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM invoices WHERE status='LUNAS'").fetchone()["s"]
        receivable = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM invoices WHERE status!='LUNAS'").fetchone()["s"]
        expense = conn.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM expenses").fetchone()["s"]
        net_profit = income - expense

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Kamar", total_rooms)
        c2.metric("Kamar Terisi", occupied)
        c3.metric("Kamar Kosong", available)
        c4.metric("Total Penghuni Aktif", active_tenants)

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Pendapatan (Lunas)", format_rp(income))
        c6.metric("Piutang Tagihan", format_rp(receivable))
        c7.metric("Pengeluaran", format_rp(expense))
        c8.metric("Laba Bersih", format_rp(net_profit))

        st.subheader("Ringkasan Keuangan")
        chart_df = pd.DataFrame(
            {"Kategori": ["Pendapatan Lunas", "Piutang", "Pengeluaran", "Laba Bersih"],
             "Jumlah (Rp)": [income, receivable, expense, net_profit]}
        ).set_index("Kategori")
        st.bar_chart(chart_df)

    elif menu == "Manajemen Kamar":
        st.header("🛏️ Manajemen Kamar")
        with st.expander("➕ Tambah Kamar Baru", expanded=True):
            with st.form("add_room_form"):
                col1, col2, col3 = st.columns(3)
                r_num = col1.text_input("Nomor Kamar (mis. A-03)")
                r_type = col2.text_input("Tipe Kamar (mis. AC + KM Dalam)")
                r_price = col3.number_input("Harga Sewa / Bulan (Rp)", min_value=0, step=50000, value=1000000)
                r_fac = st.text_input("Fasilitas Kamar", value="Kasur, Lemari, Wi-Fi")
                r_status = st.selectbox("Status", ["tersedia", "terisi", "perbaikan"])
                if st.form_submit_button("Simpan Kamar"):
                    if r_num and r_type:
                        try:
                            conn.execute(
                                "INSERT INTO rooms (room_number, room_type, monthly_price, facilities, status) VALUES (?, ?, ?, ?, ?)",
                                (r_num.strip(), r_type.strip(), int(r_price), r_fac.strip(), r_status),
                            )
                            conn.commit()
                            st.success("Kamar berhasil ditambahkan!")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Nomor kamar sudah terdaftar.")

        rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
        if rooms:
            df_rooms = pd.DataFrame([dict(r) for r in rooms])
            df_rooms["monthly_price"] = df_rooms["monthly_price"].apply(format_rp)
            st.dataframe(df_rooms, use_container_width=True, hide_index=True)

            st.subheader("Ubah Status Kamar")
            col_a, col_b, col_c = st.columns([2, 2, 1])
            room_map = {f"{r['room_number']} ({r['status']})": r["id"] for r in rooms}
            sel_room = col_a.selectbox("Pilih Kamar", list(room_map.keys()))
            new_stat = col_b.selectbox("Status Baru", ["tersedia", "terisi", "perbaikan"])
            if col_c.button("Update Status"):
                conn.execute("UPDATE rooms SET status = ? WHERE id = ?", (new_stat, room_map[sel_room]))
                conn.commit()
                st.success("Status kamar diperbarui.")
                st.rerun()

    elif menu == "Data Penghuni":
        st.header("👥 Data Penghuni")
        avail_rooms = conn.execute("SELECT * FROM rooms WHERE status='tersedia' ORDER BY room_number").fetchall()
        with st.expander("➕ Tambah Penghuni Baru & Buat Akun Login", expanded=True):
            if not avail_rooms:
                st.warning("Tidak ada kamar berstatus 'tersedia'. Tambahkan kamar atau ubah status kamar terlebih dahulu.")
            else:
                with st.form("add_tenant_form"):
                    c1, c2 = st.columns(2)
                    t_name = c1.text_input("Nama Lengkap")
                    t_wa = c2.text_input("Nomor WhatsApp (awalan 62, mis. 6281234567890)")
                    c3, c4 = st.columns(2)
                    t_email = c3.text_input("Email")
                    t_idnum = c4.text_input("No. Identitas / KTP (Opsional)")
                    t_addr = st.text_input("Alamat Asal")
                    c5, c6, c7 = st.columns(3)
                    room_opts = {f"{r['room_number']} - {r['room_type']} ({format_rp(r['monthly_price'])})": r for r in avail_rooms}
                    sel_r_label = c5.selectbox("Pilih Kamar", list(room_opts.keys()))
                    t_start = c6.date_input("Tanggal Mulai Sewa", value=datetime.now())
                    t_user = c7.text_input("Username Login Penghuni")
                    t_pass = st.text_input("Password Login Penghuni", value="kos123")
                    if st.form_submit_button("Simpan Penghuni"):
                        if t_name and t_wa and t_user and t_pass:
                            chosen_r = room_opts[sel_r_label]
                            try:
                                cur = conn.cursor()
                                cur.execute(
                                    "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, 'tenant', ?)",
                                    (t_user.strip(), hash_pw(t_pass), t_name.strip()),
                                )
                                uid = cur.lastrowid
                                cur.execute(
                                    """INSERT INTO tenants (user_id, room_id, full_name, whatsapp, email, address, id_number, start_date, monthly_rate, is_active)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                                    (uid, chosen_r["id"], t_name.strip(), t_wa.strip(), t_email.strip(), t_addr.strip(), t_idnum.strip(), str(t_start), chosen_r["monthly_price"]),
                                )
                                cur.execute("UPDATE rooms SET status = 'terisi' WHERE id = ?", (chosen_r["id"],))
                                conn.commit()
                                st.success("Penghuni dan akun portal berhasil dibuat!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Username sudah digunakan.")

        tenants = conn.execute("""
            SELECT t.id, t.full_name, u.username, r.room_number, t.whatsapp, t.email, t.start_date, t.monthly_rate, t.is_active
            FROM tenants t
            LEFT JOIN rooms r ON t.room_id = r.id
            LEFT JOIN users u ON t.user_id = u.id
            ORDER BY t.is_active DESC, t.full_name
        """).fetchall()
        if tenants:
            df_t = pd.DataFrame([dict(t) for t in tenants])
            df_t["monthly_rate"] = df_t["monthly_rate"].apply(format_rp)
            st.dataframe(df_t, use_container_width=True, hide_index=True)

    elif menu == "Tagihan & WhatsApp":
        st.header("🧾 Tagihan Bulanan & WhatsApp")
        active_tenants = conn.execute("""
            SELECT t.*, r.room_number FROM tenants t
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.is_active = 1
        """).fetchall()

        with st.expander("➕ Buat Tagihan Bulanan", expanded=True):
            if active_tenants:
                with st.form("gen_invoice_form"):
                    c1, c2, c3 = st.columns(3)
                    t_map = {f"{t['full_name']} (Kamar {t['room_number'] or '-'}) - {format_rp(t['monthly_rate'])}": t for t in active_tenants}
                    sel_t = c1.selectbox("Penghuni", list(t_map.keys()))
                    p_month = c2.text_input("Periode Bulan (YYYY-MM)", value=datetime.now().strftime("%Y-%m"))
                    due_dt = c3.date_input("Jatuh Tempo", value=datetime.now())
                    if st.form_submit_button("Buat Tagihan"):
                        t_obj = t_map[sel_t]
                        conn.execute(
                            "INSERT INTO invoices (tenant_id, period_month, amount, due_date, status) VALUES (?, ?, ?, ?, 'BELUM BAYAR')",
                            (t_obj["id"], p_month.strip(), t_obj["monthly_rate"], str(due_dt)),
                        )
                        conn.commit()
                        st.success("Tagihan berhasil dibuat!")
                        st.rerun()

        invoices = conn.execute("""
            SELECT i.*, t.full_name, t.whatsapp, r.room_number
            FROM invoices i
            JOIN tenants t ON i.tenant_id = t.id
            LEFT JOIN rooms r ON t.room_id = r.id
            ORDER BY i.id DESC
        """).fetchall()

        for inv in invoices:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
                c1.write(f"**{inv['full_name']}** (Kamar {inv['room_number'] or '-'})")
                c1.caption(f"Periode: {inv['period_month']} | Jatuh Tempo: {inv['due_date']}")
                c2.write(f"**{format_rp(inv['amount'])}**")
                c3.write(f"Status: **{inv['status']}**")

                wa_msg = quote(
                    f"Halo {inv['full_name']}, ini pengingat tagihan kos kamar {inv['room_number'] or '-'} "
                    f"periode {inv['period_month']} sebesar {format_rp(inv['amount'])} "
                    f"(jatuh tempo {inv['due_date']}). Status saat ini: {inv['status']}."
                )
                wa_url = f"https://wa.me/{inv['whatsapp']}?text={wa_msg}"
                c4.link_button("📲 Kirim Tagihan WA", wa_url)

                if inv["status"] != "LUNAS":
                    pay_rec = conn.execute("SELECT * FROM payments WHERE invoice_id = ? ORDER BY id DESC LIMIT 1", (inv["id"],)).fetchone()
                    if pay_rec:
                        st.caption(f"Metode: {pay_rec['method']} | Waktu kirim: {pay_rec['created_at']}")
                        if pay_rec["proof_file"]:
                            proof_path = os.path.join(UPLOAD_DIR, pay_rec["proof_file"])
                            if os.path.exists(proof_path):
                                st.image(proof_path, width=220, caption="Bukti Transfer")
                    if c4.button("✅ Konfirmasi LUNAS", key=f"verify_{inv['id']}"):
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        conn.execute("UPDATE invoices SET status = 'LUNAS', paid_at = ? WHERE id = ?", (now_str, inv["id"]))
                        conn.execute("UPDATE payments SET verified_by = ?, verified_at = ? WHERE invoice_id = ?", (user["id"], now_str, inv["id"]))
                        conn.commit()
                        st.success("Pembayaran dikonfirmasi LUNAS!")
                        st.rerun()

    elif menu == "Pengeluaran & Laporan":
        st.header("💰 Pengeluaran & Laporan Keuangan")
        with st.form("add_exp_form"):
            c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
            cat = c1.selectbox("Kategori", ["Listrik", "Air", "Internet/Wi-Fi", "Kebersihan", "Perbaikan Kamar", "Gaji Penjaga", "Perlengkapan", "Lainnya"])
            amt = c2.number_input("Nominal (Rp)", min_value=0, step=10000)
            exp_dt = c3.date_input("Tanggal", value=datetime.now())
            desc = c4.text_input("Keterangan")
            if st.form_submit_button("Catat Pengeluaran"):
                if amt > 0:
                    conn.execute(
                        "INSERT INTO expenses (category, amount, expense_date, description) VALUES (?, ?, ?, ?)",
                        (cat, int(amt), str(exp_dt), desc.strip()),
                    )
                    conn.commit()
                    st.success("Pengeluaran berhasil dicatat.")
                    st.rerun()

        expenses = conn.execute("SELECT * FROM expenses ORDER BY expense_date DESC").fetchall()
        if expenses:
            df_exp = pd.DataFrame([dict(e) for e in expenses])
            st.subheader("Riwayat Pengeluaran")
            st.dataframe(df_exp, use_container_width=True, hide_index=True)

            csv_data = df_exp.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Unduh Laporan Pengeluaran (CSV)", csv_data, "laporan_pengeluaran.csv", "text/csv")

        inv_all = conn.execute("""
            SELECT i.id, t.full_name AS penghuni, r.room_number AS kamar, i.period_month AS periode, i.amount AS nominal, i.status, i.paid_at
            FROM invoices i JOIN tenants t ON i.tenant_id = t.id LEFT JOIN rooms r ON t.room_id = r.id
        """).fetchall()
        if inv_all:
            df_inv = pd.DataFrame([dict(x) for x in inv_all])
            st.subheader("Rekap Pembayaran & Piutang")
            st.dataframe(df_inv, use_container_width=True, hide_index=True)
            csv_inv = df_inv.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Unduh Rekap Tagihan & Pendapatan (CSV)", csv_inv, "rekap_tagihan.csv", "text/csv")

    elif menu == "Keluhan Penghuni":
        st.header("🛠️ Daftar Keluhan Penghuni")
        comps = conn.execute("""
            SELECT c.*, t.full_name, r.room_number
            FROM complaints c
            JOIN tenants t ON c.tenant_id = t.id
            LEFT JOIN rooms r ON t.room_id = r.id
            ORDER BY c.id DESC
        """).fetchall()
        if not comps:
            st.info("Belum ada keluhan masuk.")
        for c in comps:
            with st.container(border=True):
                st.write(f"**{c['title']}** — {c['full_name']} (Kamar {c['room_number'] or '-'})")
                st.write(c["description"])
                st.caption(f"Waktu: {c['created_at']} | Status: {c['status']}")
                if c["status"] != "SELESAI":
                    if st.button("Tandai Selesai", key=f"comp_{c['id']}"):
                        conn.execute("UPDATE complaints SET status = 'SELESAI' WHERE id = ?", (c["id"],))
                        conn.commit()
                        st.rerun()

    elif menu == "Pengaturan Kos":
        st.header("⚙️ Pengaturan Identitas & Rekening Kos")
        bank_val = conn.execute("SELECT value FROM settings WHERE key='bank_info'").fetchone()
        kos_val = conn.execute("SELECT value FROM settings WHERE key='kos_name'").fetchone()
        with st.form("settings_form"):
            new_kos = st.text_input("Nama Kos", value=kos_val["value"] if kos_val else "")
            new_bank = st.text_input("Info Rekening / QRIS Pembayaran", value=bank_val["value"] if bank_val else "")
            if st.form_submit_button("Simpan Pengaturan"):
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('kos_name', ?)", (new_kos.strip(),))
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bank_info', ?)", (new_bank.strip(),))
                conn.commit()
                st.success("Pengaturan tersimpan.")

    conn.close()


def tenant_view():
    user = st.session_state.user
    conn = get_db()
    tenant = conn.execute("""
        SELECT t.*, r.room_number, r.room_type, r.facilities
        FROM tenants t LEFT JOIN rooms r ON t.room_id = r.id
        WHERE t.user_id = ?
    """, (user["id"],)).fetchone()
    bank_info = conn.execute("SELECT value FROM settings WHERE key='bank_info'").fetchone()

    with st.sidebar:
        st.title("🏠 Portal Penghuni")
        st.write(f"Halo, **{user['full_name']}**")
        if st.button("Keluar", use_container_width=True):
            st.session_state.user = None
            st.rerun()

    st.header("Portal Penghuni Kos")
    if not tenant:
        st.warning("Data penghuni belum terhubung dengan kamar. Hubungi admin kos.")
        conn.close()
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Kamar", f"{tenant['room_number'] or '-'}")
    c2.metric("Tipe Kamar", f"{tenant['room_type'] or '-'}")
    c3.metric("Tarif Bulanan", format_rp(tenant["monthly_rate"]))
    st.info(f"**Fasilitas Kamar:** {tenant['facilities'] or '-'} | **Rekening Tujuan Pembayaran:** {bank_info['value'] if bank_info else '-'}")

    tab1, tab2 = st.tabs(["💳 Tagihan & Pembayaran", "🛠️ Kirim Keluhan"])

    with tab1:
        invoices = conn.execute("SELECT * FROM invoices WHERE tenant_id = ? ORDER BY id DESC", (tenant["id"],)).fetchall()
        if not invoices:
            st.write("Belum ada tagihan.")
        for inv in invoices:
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 2, 3])
                col1.write(f"**Periode {inv['period_month']}**")
                col1.caption(f"Jatuh tempo: {inv['due_date']}")
                col2.write(f"**{format_rp(inv['amount'])}**")
                col2.write(f"Status: **{inv['status']}**")

                if inv["status"] == "BELUM BAYAR":
                    with col3.form(f"pay_form_{inv['id']}"):
                        method = st.selectbox("Metode", ["Transfer Manual", "QRIS", "Virtual Account"], key=f"m_{inv['id']}")
                        proof = st.file_uploader("Upload Bukti Transfer", type=["png", "jpg", "jpeg"], key=f"f_{inv['id']}")
                        if st.form_submit_button("Konfirmasi Bayar"):
                            fname = None
                            if proof is not None:
                                fname = f"{inv['id']}_{proof.name}"
                                with open(os.path.join(UPLOAD_DIR, fname), "wb") as f:
                                    f.write(proof.getbuffer())
                            conn.execute(
                                "INSERT INTO payments (invoice_id, method, amount, proof_file) VALUES (?, ?, ?, ?)",
                                (inv["id"], method, inv["amount"], fname),
                            )
                            conn.execute("UPDATE invoices SET status = 'MENUNGGU VERIFIKASI' WHERE id = ?", (inv["id"],))
                            conn.commit()
                            st.success("Konfirmasi pembayaran dikirim! Menunggu verifikasi admin.")
                            st.rerun()
                elif inv["status"] == "LUNAS":
                    receipt = (
                        f"BUKTI PEMBAYARAN LUNAS - KOS MANAGER\n"
                        f"Nama: {tenant['full_name']}\n"
                        f"Kamar: {tenant['room_number']}\n"
                        f"Periode: {inv['period_month']}\n"
                        f"Nominal: {format_rp(inv['amount'])} (LUNAS)\n"
                        f"Tanggal Lunas: {inv['paid_at'] or '-'}\n"
                    )
                    col3.download_button(
                        "📄 Unduh Kwitansi",
                        receipt,
                        file_name=f"kwitansi_{inv['period_month']}.txt",
                        key=f"dl_{inv['id']}",
                    )

    with tab2:
        with st.form("complaint_form"):
            title = st.text_input("Judul Keluhan (mis. Keran air bocor)")
            desc = st.text_area("Detail Keluhan")
            if st.form_submit_button("Kirim Keluhan"):
                if title and desc:
                    conn.execute(
                        "INSERT INTO complaints (tenant_id, title, description) VALUES (?, ?, ?)",
                        (tenant["id"], title.strip(), desc.strip()),
                    )
                    conn.commit()
                    st.success("Keluhan terkirim ke admin.")
                    st.rerun()

        my_comps = conn.execute("SELECT * FROM complaints WHERE tenant_id = ? ORDER BY id DESC", (tenant["id"],)).fetchall()
        if my_comps:
            st.subheader("Riwayat Keluhan Saya")
            st.dataframe(pd.DataFrame([dict(c) for c in my_comps]), use_container_width=True, hide_index=True)

    conn.close()


if st.session_state.user is None:
    login_view()
elif st.session_state.user["role"] == "admin":
    admin_view()
else:
    tenant_view()
