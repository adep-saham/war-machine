import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Gold War Room (MVP)", layout="wide")
DB_PATH = "gold_war_room.db"

# =========================
# DB HELPERS
# =========================
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_product (
        product_id TEXT PRIMARY KEY,
        product_name TEXT,
        pecahan_gram REAL,
        category TEXT DEFAULT 'retail'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_competitor (
        competitor_id TEXT PRIMARY KEY,
        competitor_name TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fact_price (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        source_type TEXT,               -- 'COMPETITOR' or 'COMPANY'
        competitor_id TEXT,             -- nullable for COMPANY
        product_id TEXT,
        price_sell REAL,
        price_buy REAL,
        promo_cashback REAL DEFAULT 0,  -- Rp
        promo_discount REAL DEFAULT 0,  -- Rp
        shipping_fee REAL DEFAULT 0,    -- Rp
        admin_fee REAL DEFAULT 0,       -- Rp
        notes TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fact_cost_guardrail (
        product_id TEXT PRIMARY KEY,
        hpp REAL,               -- Rp per unit (per pecahan)
        floor_margin_pct REAL,  -- minimal margin %
        floor_price REAL        -- minimal price sell (optional)
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_fact_price_ts ON fact_price(ts);
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_fact_price_prod ON fact_price(product_id);
    """)

    conn.commit()
    conn.close()

def upsert_dim_product(df: pd.DataFrame):
    conn = get_conn()
    df = df.copy()
    df["product_id"] = df["product_id"].astype(str)
    df[["product_name","category"]] = df[["product_name","category"]].fillna("")
    df.to_sql("dim_product", conn, if_exists="append", index=False)
    # de-dup keep first
    conn.execute("""
        DELETE FROM dim_product
        WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM dim_product GROUP BY product_id
        )
    """)
    conn.commit()
    conn.close()

def upsert_dim_competitor(names):
    conn = get_conn()
    cur = conn.cursor()
    for n in names:
        cid = n.strip().upper().replace(" ", "_")
        cur.execute("INSERT OR IGNORE INTO dim_competitor(competitor_id, competitor_name) VALUES (?,?)", (cid, n.strip()))
    conn.commit()
    conn.close()

def upsert_guardrail(product_id, hpp, floor_margin_pct, floor_price):
    conn = get_conn()
    conn.execute("""
        INSERT INTO fact_cost_guardrail(product_id, hpp, floor_margin_pct, floor_price)
        VALUES (?,?,?,?)
        ON CONFLICT(product_id) DO UPDATE SET
            hpp=excluded.hpp,
            floor_margin_pct=excluded.floor_margin_pct,
            floor_price=excluded.floor_price
    """, (product_id, float(hpp), float(floor_margin_pct), float(floor_price)))
    conn.commit()
    conn.close()

def insert_prices(df: pd.DataFrame):
    conn = get_conn()
    df = df.copy()
    df.to_sql("fact_price", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

def read_table(sql, params=None):
    conn = get_conn()
    out = pd.read_sql_query(sql, conn, params=params or [])
    conn.close()
    return out

# =========================
# BUSINESS LOGIC
# =========================
def effective_price(row):
    # Effective = sell - cashback - discount + shipping + admin
    return (row["price_sell"] - row["promo_cashback"] - row["promo_discount"] + row["shipping_fee"] + row["admin_fee"])

def war_score(gap_pct, volatility_proxy, promo_intensity):
    # Simple scoring: bigger negative gap (we are more expensive) increases risk
    # gap_pct = (our_eff - min_comp_eff)/min_comp_eff
    # if gap_pct > 0 => we are pricier => risk
    return (
        60 * np.clip(gap_pct, 0, 0.2) / 0.2
        + 25 * np.clip(volatility_proxy, 0, 1)
        + 15 * np.clip(promo_intensity, 0, 1)
    )

def recommend_price(our_eff, min_comp_eff, guard_floor_price, hpp, floor_margin_pct, mode="DEFENSIVE"):
    """
    Defensive: target match competitor effective price (or slightly below)
    Neutral: close half-way to competitor
    Aggressive: undercut competitor by small step
    Guardrails: not below floor price and not below (hpp * (1+margin))
    """
    step = 500  # Rp step undercut (MVP)
    if mode == "AGGRESSIVE":
        target = min_comp_eff - step
    elif mode == "NEUTRAL":
        target = our_eff - (our_eff - min_comp_eff) * 0.5
    else:
        target = min_comp_eff  # match

    # Compute min allowed by margin floor
    min_by_margin = hpp * (1 + floor_margin_pct/100.0)
    floor = max(guard_floor_price, min_by_margin)

    final = max(target, floor)
    return float(final), float(floor)

# =========================
# UI
# =========================
init_db()

st.title("🏆 Gold War Room (MVP) — Streamlit")
st.caption("Monitor harga kompetitor, gap, alert, dan rekomendasi harga berbasis rule + guardrail (SQLite local).")

tabs = st.tabs([
    "1) Master Produk & Guardrail",
    "2) Input Harga (Company & Competitor)",
    "3) War Room Dashboard",
    "4) Data Explorer"
])

# -------------------------
# TAB 1: MASTER
# -------------------------
with tabs[0]:
    st.subheader("1) Master Produk")
    st.write("Definisikan produk/pecahan yang dipantau.")

    colA, colB = st.columns([2,1])
    with colA:
        st.markdown("**Tambah produk (manual)**")
        with st.form("add_product", clear_on_submit=False):
            product_id = st.text_input("product_id (unik)", value="ANTAM_1G")
            product_name = st.text_input("product_name", value="Emas Batangan 1g")
            pecahan_gram = st.number_input("pecahan_gram", min_value=0.1, value=1.0, step=0.5)
            category = st.selectbox("category", ["retail","investasi","lainnya"], index=0)
            submitted = st.form_submit_button("Simpan Produk")
            if submitted:
                dfp = pd.DataFrame([{
                    "product_id": product_id.strip().upper(),
                    "product_name": product_name.strip(),
                    "pecahan_gram": float(pecahan_gram),
                    "category": category
                }])
                upsert_dim_product(dfp)
                st.success("Produk tersimpan.")

        st.markdown("**Upload master produk (CSV)**")
        st.caption("Kolom wajib: product_id, product_name, pecahan_gram, category")
        up = st.file_uploader("Upload CSV master produk", type=["csv"], key="upload_master")
        if up:
            dfm = pd.read_csv(up)
            needed = {"product_id","product_name","pecahan_gram","category"}
            if not needed.issubset(set(dfm.columns)):
                st.error(f"Kolom kurang. Wajib: {needed}")
            else:
                dfm["product_id"] = dfm["product_id"].astype(str).str.upper().str.strip()
                upsert_dim_product(dfm[list(needed)])
                st.success("Master produk ter-upload & tersimpan.")

    with colB:
        st.markdown("**Daftar Produk**")
        prod = read_table("SELECT * FROM dim_product ORDER BY pecahan_gram ASC")
        st.dataframe(prod, use_container_width=True)

    st.divider()
    st.subheader("2) Guardrail Biaya & Margin (Anti bunuh margin)")
    st.write("Set **HPP** dan **minimal margin** per produk (per pecahan).")

    prod = read_table("SELECT * FROM dim_product ORDER BY pecahan_gram ASC")
    if prod.empty:
        st.warning("Tambahkan produk dulu.")
    else:
        pid = st.selectbox("Pilih product_id", prod["product_id"].tolist())
        current = read_table("SELECT * FROM fact_cost_guardrail WHERE product_id=?", [pid])
        if current.empty:
            hpp0, m0, fp0 = 0.0, 2.0, 0.0
        else:
            hpp0 = float(current.loc[0,"hpp"])
            m0 = float(current.loc[0,"floor_margin_pct"])
            fp0 = float(current.loc[0,"floor_price"])

        c1, c2, c3, c4 = st.columns([1,1,1,1])
        with c1:
            hpp = st.number_input("HPP (Rp/unit pecahan)", min_value=0.0, value=hpp0, step=1000.0)
        with c2:
            floor_margin_pct = st.number_input("Floor margin (%)", min_value=0.0, value=m0, step=0.5)
        with c3:
            floor_price = st.number_input("Floor price (Rp) (opsional)", min_value=0.0, value=fp0, step=1000.0)
        with c4:
            if st.button("Simpan Guardrail"):
                upsert_guardrail(pid, hpp, floor_margin_pct, floor_price)
                st.success("Guardrail tersimpan.")

        st.caption("Guardrail digunakan oleh engine rekomendasi agar tidak menyarankan harga di bawah batas aman.")
        gr = read_table("SELECT * FROM fact_cost_guardrail")
        st.dataframe(gr, use_container_width=True)

# -------------------------
# TAB 2: INPUT HARGA
# -------------------------
with tabs[1]:
    st.subheader("Input Harga Company & Competitor")
    st.write("Masukkan harga terbaru (bisa intrahari). Sistem akan menyimpan histori.")

    prod = read_table("SELECT * FROM dim_product ORDER BY pecahan_gram ASC")
    comp = read_table("SELECT * FROM dim_competitor ORDER BY competitor_name ASC")

    if prod.empty:
        st.warning("Tambahkan master produk dulu di Tab 1.")
    else:
        left, right = st.columns(2)

        # COMPANY INPUT
        with left:
            st.markdown("### 🟢 Harga Company (Anda)")
            with st.form("company_price"):
                pid = st.selectbox("Product", prod["product_id"].tolist(), key="cp_pid")
                price_sell = st.number_input("Harga jual", min_value=0.0, value=0.0, step=1000.0, key="cp_sell")
                price_buy = st.number_input("Harga buyback", min_value=0.0, value=0.0, step=1000.0, key="cp_buy")
                promo_cashback = st.number_input("Cashback (Rp)", min_value=0.0, value=0.0, step=1000.0, key="cp_cb")
                promo_discount = st.number_input("Discount (Rp)", min_value=0.0, value=0.0, step=1000.0, key="cp_disc")
                shipping_fee = st.number_input("Ongkir (Rp)", min_value=0.0, value=0.0, step=1000.0, key="cp_ship")
                admin_fee = st.number_input("Admin fee (Rp)", min_value=0.0, value=0.0, step=1000.0, key="cp_admin")
                notes = st.text_input("Catatan", value="")

                save = st.form_submit_button("Simpan Harga Company")
                if save:
                    df = pd.DataFrame([{
                        "ts": datetime.utcnow().isoformat(),
                        "source_type": "COMPANY",
                        "competitor_id": None,
                        "product_id": pid,
                        "price_sell": float(price_sell),
                        "price_buy": float(price_buy),
                        "promo_cashback": float(promo_cashback),
                        "promo_discount": float(promo_discount),
                        "shipping_fee": float(shipping_fee),
                        "admin_fee": float(admin_fee),
                        "notes": notes
                    }])
                    insert_prices(df)
                    st.success("Harga company tersimpan.")

        # COMPETITOR INPUT
        with right:
            st.markdown("### 🔴 Harga Competitor")
            with st.form("add_comp"):
                new_comp = st.text_input("Tambah competitor (opsional)", value="")
                addc = st.form_submit_button("Tambahkan Competitor")
                if addc and new_comp.strip():
                    upsert_dim_competitor([new_comp.strip()])
                    st.success("Competitor ditambahkan. Refresh jika belum muncul.")

            comp = read_table("SELECT * FROM dim_competitor ORDER BY competitor_name ASC")
            if comp.empty:
                st.info("Tambahkan minimal 1 competitor dulu.")
            else:
                with st.form("competitor_price"):
                    cid = st.selectbox("Competitor", comp["competitor_id"].tolist(), format_func=lambda x: comp.set_index("competitor_id").loc[x,"competitor_name"])
                    pid2 = st.selectbox("Product", prod["product_id"].tolist(), key="kp_pid")
                    price_sell2 = st.number_input("Harga jual", min_value=0.0, value=0.0, step=1000.0, key="kp_sell")
                    price_buy2 = st.number_input("Harga buyback", min_value=0.0, value=0.0, step=1000.0, key="kp_buy")
                    promo_cashback2 = st.number_input("Cashback (Rp)", min_value=0.0, value=0.0, step=1000.0, key="kp_cb")
                    promo_discount2 = st.number_input("Discount (Rp)", min_value=0.0, value=0.0, step=1000.0, key="kp_disc")
                    shipping_fee2 = st.number_input("Ongkir (Rp)", min_value=0.0, value=0.0, step=1000.0, key="kp_ship")
                    admin_fee2 = st.number_input("Admin fee (Rp)", min_value=0.0, value=0.0, step=1000.0, key="kp_admin")
                    notes2 = st.text_input("Catatan", value="", key="kp_notes")

                    save2 = st.form_submit_button("Simpan Harga Competitor")
                    if save2:
                        df2 = pd.DataFrame([{
                            "ts": datetime.utcnow().isoformat(),
                            "source_type": "COMPETITOR",
                            "competitor_id": cid,
                            "product_id": pid2,
                            "price_sell": float(price_sell2),
                            "price_buy": float(price_buy2),
                            "promo_cashback": float(promo_cashback2),
                            "promo_discount": float(promo_discount2),
                            "shipping_fee": float(shipping_fee2),
                            "admin_fee": float(admin_fee2),
                            "notes": notes2
                        }])
                        insert_prices(df2)
                        st.success("Harga competitor tersimpan.")

    st.divider()
    st.subheader("Upload harga massal (CSV)")
    st.caption("Kolom wajib: source_type, competitor_id (boleh kosong untuk COMPANY), product_id, price_sell, price_buy, promo_cashback, promo_discount, shipping_fee, admin_fee, notes")
    up_prices = st.file_uploader("Upload CSV harga", type=["csv"], key="upload_prices")
    if up_prices:
        dfu = pd.read_csv(up_prices)
        required = {"source_type","product_id","price_sell","price_buy","promo_cashback","promo_discount","shipping_fee","admin_fee","notes"}
        if not required.issubset(set(dfu.columns)):
            st.error(f"Kolom kurang. Wajib: {required}")
        else:
            dfu["ts"] = datetime.utcnow().isoformat()
            if "competitor_id" not in dfu.columns:
                dfu["competitor_id"] = None
            dfu["source_type"] = dfu["source_type"].astype(str).str.upper().str.strip()
            dfu["product_id"] = dfu["product_id"].astype(str).str.upper().str.strip()
            dfu["competitor_id"] = dfu["competitor_id"].where(dfu["competitor_id"].notna(), None)
            insert_prices(dfu[[
                "ts","source_type","competitor_id","product_id",
                "price_sell","price_buy","promo_cashback","promo_discount",
                "shipping_fee","admin_fee","notes"
            ]])
            st.success("Harga massal tersimpan.")

# -------------------------
# TAB 3: WAR ROOM
# -------------------------
with tabs[2]:
    st.subheader("War Room Dashboard (MVP)")
    st.write("Menggunakan snapshot harga terbaru per produk untuk company dan competitor.")

    prod = read_table("SELECT * FROM dim_product ORDER BY pecahan_gram ASC")
    if prod.empty:
        st.warning("Tambahkan produk dulu.")
    else:
        # Get latest prices per (source_type, competitor_id, product_id)
        prices = read_table("""
        SELECT * FROM fact_price
        """)
        if prices.empty:
            st.info("Belum ada data harga. Input di Tab 2 dulu.")
        else:
            prices["ts"] = pd.to_datetime(prices["ts"])
            # latest per key
            prices = prices.sort_values("ts").groupby(["source_type","competitor_id","product_id"], dropna=False).tail(1)

            # separate company snapshot
            company = prices[prices["source_type"]=="COMPANY"].copy()
            comp = prices[prices["source_type"]=="COMPETITOR"].copy()

            if company.empty:
                st.warning("Belum ada harga COMPANY.")
            elif comp.empty:
                st.warning("Belum ada harga COMPETITOR.")
            else:
                # compute effective prices
                for df in [company, comp]:
                    for c in ["promo_cashback","promo_discount","shipping_fee","admin_fee"]:
                        df[c] = df[c].fillna(0.0)
                    df["eff_price"] = df.apply(effective_price, axis=1)

                # attach competitor names
                comp_dim = read_table("SELECT * FROM dim_competitor")
                comp = comp.merge(comp_dim, how="left", on="competitor_id")

                # compute per product: min competitor effective price
                min_comp = comp.groupby("product_id")["eff_price"].min().reset_index().rename(columns={"eff_price":"min_comp_eff"})
                # compute per product: which competitor is min
                min_comp_who = comp.sort_values("eff_price").groupby("product_id").head(1)[["product_id","competitor_name","eff_price"]]
                min_comp_who = min_comp_who.rename(columns={"competitor_name":"min_competitor","eff_price":"min_comp_eff_check"})
                min_comp = min_comp.merge(min_comp_who, on="product_id", how="left")

                # join with company
                war = company.merge(min_comp, on="product_id", how="left")
                war = war.merge(prod[["product_id","product_name","pecahan_gram"]], on="product_id", how="left")

                # volatility proxy (MVP): using dispersion of competitor eff price per product
                vol = comp.groupby("product_id")["eff_price"].apply(lambda s: float(np.std(s)/max(np.mean(s),1))).reset_index().rename(columns={"eff_price":"vol_proxy"})
                war = war.merge(vol, on="product_id", how="left")
                war["vol_proxy"] = war["vol_proxy"].fillna(0.0)

                # promo intensity proxy: competitor share having promo
                comp["has_promo"] = ((comp["promo_cashback"]>0) | (comp["promo_discount"]>0)).astype(int)
                promo = comp.groupby("product_id")["has_promo"].mean().reset_index().rename(columns={"has_promo":"promo_intensity"})
                war = war.merge(promo, on="product_id", how="left")
                war["promo_intensity"] = war["promo_intensity"].fillna(0.0)

                # gap
                war["gap_pct"] = (war["eff_price"] - war["min_comp_eff"]) / war["min_comp_eff"]
                war["gap_rp"] = war["eff_price"] - war["min_comp_eff"]

                # score & status
                war["war_score"] = war.apply(lambda r: war_score(r["gap_pct"], r["vol_proxy"], r["promo_intensity"]), axis=1)
                war["status"] = pd.cut(
                    war["war_score"],
                    bins=[-1, 30, 60, 1000],
                    labels=["NORMAL","WARNING","ATTACK"]
                )

                # Guardrail join
                gr = read_table("SELECT * FROM fact_cost_guardrail")
                war = war.merge(gr, on="product_id", how="left")
                war["hpp"] = war["hpp"].fillna(0.0)
                war["floor_margin_pct"] = war["floor_margin_pct"].fillna(0.0)
                war["floor_price"] = war["floor_price"].fillna(0.0)

                # Strategy mode
                mode = st.selectbox("Mode strategi", ["DEFENSIVE","NEUTRAL","AGGRESSIVE"], index=0)

                # Recommendation
                recs = []
                for _, r in war.iterrows():
                    rec_price, floor = recommend_price(
                        our_eff=float(r["eff_price"]),
                        min_comp_eff=float(r["min_comp_eff"]),
                        guard_floor_price=float(r["floor_price"]),
                        hpp=float(r["hpp"]),
                        floor_margin_pct=float(r["floor_margin_pct"]),
                        mode=mode
                    )
                    recs.append((rec_price, floor))
                war["rec_eff_price"] = [x[0] for x in recs]
                war["floor_guard"] = [x[1] for x in recs]
                war["delta_to_rec"] = war["rec_eff_price"] - war["eff_price"]

                # KPIs top
                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.metric("Produk dipantau", int(war.shape[0]))
                with k2:
                    st.metric("ATTACK", int((war["status"]=="ATTACK").sum()))
                with k3:
                    st.metric("WARNING", int((war["status"]=="WARNING").sum()))
                with k4:
                    worst = war.sort_values("war_score", ascending=False).head(1)
                    if not worst.empty:
                        st.metric("Worst war_score", f"{float(worst['war_score'].iloc[0]):.1f}")

                st.divider()

                # Table view
                show_cols = [
                    "product_id","product_name","pecahan_gram",
                    "eff_price","min_comp_eff","min_competitor",
                    "gap_rp","gap_pct","war_score","status",
                    "rec_eff_price","delta_to_rec","floor_guard"
                ]
                view = war[show_cols].copy()
                view["gap_pct"] = (view["gap_pct"]*100).round(2)
                view = view.sort_values(["status","war_score"], ascending=[False, False])

                st.markdown("### 📌 War Table (snapshot terbaru)")
                st.dataframe(view, use_container_width=True)

                st.markdown("### 🔍 Detail Competitor per Produk")
                pid_focus = st.selectbox("Pilih produk untuk lihat detail kompetitor", prod["product_id"].tolist())
                det = comp[comp["product_id"]==pid_focus].copy()
                det_show = det[[
                    "competitor_name","price_sell","promo_cashback","promo_discount",
                    "shipping_fee","admin_fee","eff_price","ts","notes"
                ]].sort_values("eff_price")
                st.dataframe(det_show, use_container_width=True)

                st.caption("Catatan: MVP ini pakai proksi volatilitas & promo sederhana. Nanti bisa ditingkatkan jadi model yang lebih canggih.")

# -------------------------
# TAB 4: EXPLORER
# -------------------------
with tabs[3]:
    st.subheader("Data Explorer")
    st.write("Cek data mentah yang tersimpan di SQLite.")

    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**dim_product**")
        st.dataframe(read_table("SELECT * FROM dim_product ORDER BY pecahan_gram"), use_container_width=True)
        st.markdown("**dim_competitor**")
        st.dataframe(read_table("SELECT * FROM dim_competitor ORDER BY competitor_name"), use_container_width=True)
    with t2:
        st.markdown("**fact_cost_guardrail**")
        st.dataframe(read_table("SELECT * FROM fact_cost_guardrail"), use_container_width=True)
        st.markdown("**fact_price (latest 200)**")
        st.dataframe(read_table("SELECT * FROM fact_price ORDER BY ts DESC LIMIT 200"), use_container_width=True)

    st.divider()
    if st.button("⚠️ Reset DB (hapus semua data)", type="secondary"):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS fact_price")
        cur.execute("DROP TABLE IF EXISTS fact_cost_guardrail")
        cur.execute("DROP TABLE IF EXISTS dim_product")
        cur.execute("DROP TABLE IF EXISTS dim_competitor")
        conn.commit()
        conn.close()
        init_db()
        st.success("DB di-reset. Refresh halaman.")
