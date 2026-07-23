"""
SoundCraft First-Touch Agent — Customer Chat
"""
import json
from pathlib import Path

import duckdb
import streamlit as st

from agent.startup import ensure_db
from agent.soundcraft_agent import SoundCraftAgent

ensure_db()  # no-op if DB already exists; seeds on Streamlit Cloud cold start

from agent.startup import get_db_path
DB_PATH = get_db_path()

st.set_page_config(
    page_title="SoundCraft | Find Your Sound",
    page_icon="🎵",
    layout="wide",
)

st.markdown("""
<style>
    .handoff-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #e85d04;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-top: 1rem;
    }
    .handoff-title { color: #e85d04; font-size: 0.85rem; font-weight: 700;
                     letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.5rem; }
    .escalation-card {
        background: linear-gradient(135deg, #1a2e1a 0%, #163e16 100%);
        border: 1px solid #2ecc71; border-radius: 12px;
        padding: 1.2rem 1.5rem; margin-top: 1rem;
    }
    .product-card {
        background: #1e1e2e; border: 1px solid #3a3a5c;
        border-radius: 10px; padding: 0.9rem 1rem; margin-bottom: 0.6rem;
    }
    .product-name  { font-weight: 700; font-size: 1rem; margin-bottom: 0.2rem; }
    .product-price { color: #f39c12; font-weight: 700; font-size: 1.1rem; }
    .product-desc  { color: #aaa; font-size: 0.85rem; margin-top: 0.3rem; }
    .product-badge { background: #2c3e50; border-radius: 4px; padding: 2px 7px;
                     font-size: 0.75rem; color: #ccc; margin-right: 4px; }
    /* Product tile list */
    .product-grid {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 8px;
    }
    .product-tile {
        background: #1a1a2e;
        border: 1px solid #e85d04;
        border-radius: 10px;
        padding: 10px 12px;
        display: flex;
        flex-direction: column;
        gap: 3px;
    }
    .tile-brand { color: #e85d04; font-weight: 600; font-size: 0.75rem; }
    .tile-name  { font-weight: 700; font-size: 0.88rem; }
    .tile-price { color: #f39c12; font-weight: 700; font-size: 0.95rem; }
    .tile-desc  { color: #aaa; font-size: 0.76rem; line-height: 1.35; }
    .tile-meta  { margin-top: 2px; }
    .tile-stock-in   { font-size: 0.75rem; color: #4caf50; }
    .tile-stock-low  { font-size: 0.75rem; color: #ff9800; font-weight: 600; }
    .tile-stock-out  { font-size: 0.75rem; color: #f44336; }
    .jamie-picks-banner {
        background: linear-gradient(90deg, #1a1a2e, #16213e);
        border-left: 3px solid #e85d04;
        border-radius: 6px;
        padding: 8px 14px;
        margin-bottom: 4px;
        color: #e85d04;
        font-weight: 600;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.image("assets/soundcraft_logo.png", width=320)
st.caption("Your personal gear advisor — powered by AI, backed by human experts")
st.divider()


def _safe_md(text: str) -> str:
    return text.replace('$', '&#36;')


# ── Product helpers ───────────────────────────────────────────────────────────

def fetch_products(product_ids: list[str]) -> list[dict]:
    if not DB_PATH.exists() or not product_ids:
        return []
    seen = set()
    product_ids = [p for p in product_ids if not (p in seen or seen.add(p))]
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        placeholders = ",".join(["?"] * len(product_ids))
        rows = con.execute(
            f"""SELECT p.product_id, p.product_name, p.brand, p.category, p.price,
                       p.description, p.skill_level, p.use_case, p.price_tier,
                       p.manufacturer_url, p.in_stock, i.quantity
                FROM main.dim_products p
                LEFT JOIN main.inventory i USING (product_id)
                WHERE p.product_id IN ({placeholders})""",
            product_ids,
        ).fetchall()
        cols = ["product_id", "product_name", "brand", "category", "price",
                "description", "skill_level", "use_case", "price_tier",
                "manufacturer_url", "in_stock", "quantity"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def browse_products(categories: list[str], max_price: float) -> list[dict]:
    if not DB_PATH.exists():
        return []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        params: list = [max_price]
        where = "p.price <= ?"
        if categories:
            placeholders = ",".join(["?"] * len(categories))
            where += f" AND p.category IN ({placeholders})"
            params.extend(categories)
        rows = con.execute(
            f"""SELECT p.product_id, p.product_name, p.brand, p.category, p.price,
                       p.description, p.skill_level, p.use_case, p.price_tier,
                       p.in_stock, i.quantity
                FROM main.dim_products p
                LEFT JOIN main.inventory i USING (product_id)
                WHERE {where} AND NOT p.product_name LIKE '%Bundle%'
                ORDER BY p.category, p.price
                LIMIT 12""",
            params,
        ).fetchall()
        cols = ["product_id", "product_name", "brand", "category", "price",
                "description", "skill_level", "use_case", "price_tier", "in_stock", "quantity"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def render_product_cards(product_ids: list[str]):
    """Inline cards shown inside chat messages."""
    seen = set()
    product_ids = [p for p in product_ids if not (p in seen or seen.add(p))]
    products = fetch_products(product_ids)
    if not products:
        return
    st.markdown("---")
    st.markdown("**Recommended for you:**")
    for p in products:
        price = float(p["price"]) if p["price"] else 0
        mfr_url = p.get("manufacturer_url", "")
        link_html = (
            f'<a href="{mfr_url}" target="_blank" style="color:#3498db;font-size:0.82rem;">'
            f'→ Visit {p["brand"]} website</a>'
        ) if mfr_url else ""

        st.markdown(f"""
        <div class="product-card">
            <div class="product-name">{p['product_name']}</div>
            <div class="product-price">${price:,.2f}
                <span class="product-badge">{p.get('price_tier','')}</span>
                <span class="product-badge">{p.get('skill_level','')}</span>
                <span class="product-badge">{p.get('use_case','')}</span>
            </div>
            <div class="product-desc">{p['description']}</div>
            <div style="margin-top:0.5rem">{link_html}</div>
        </div>
        """, unsafe_allow_html=True)


def render_product_tiles(products: list[dict]):
    """CSS grid of tiles for the browse pane."""
    if not products:
        st.markdown(
            '<p style="color:#666;text-align:center;padding:28px">'
            'Use the filters above or chat with Jamie to see products here.</p>',
            unsafe_allow_html=True,
        )
        return
    tiles = []
    for p in products:
        price = float(p["price"]) if p["price"] else 0
        qty = p.get("quantity")
        qty = int(qty) if qty is not None else None
        if qty is None or qty == 0:
            stock = '<span class="tile-stock-out">&#9679; Out of Stock</span>'
        elif qty == 1:
            stock = '<span class="tile-stock-low">&#9679; Last One!</span>'
        elif qty < 10:
            stock = f'<span class="tile-stock-low">&#9679; Only {qty} left</span>'
        else:
            stock = f'<span class="tile-stock-in">&#9679; {qty} in stock</span>'
        desc = (p.get("description") or "")[:120]
        tiles.append(f"""
        <div class="product-tile">
            <div class="tile-brand">{p.get('brand', '')} &mdash; {p.get('category', '')}</div>
            <div class="tile-name">{p['product_name']}</div>
            <div class="tile-price">${price:,.2f}
                <span class="product-badge">{p.get('price_tier', '')}</span>
            </div>
            <div class="tile-desc">{desc}</div>
            <div class="tile-meta">
                <span class="product-badge">{p.get('skill_level', '')}</span>
                <span class="product-badge">{p.get('use_case', '')}</span>
            </div>
            <div style="margin-top:6px">{stock}</div>
        </div>""")
    st.markdown(
        f'<div class="product-grid">{"".join(tiles)}</div>',
        unsafe_allow_html=True,
    )


# ── Session state ─────────────────────────────────────────────────────────────
if "agent" not in st.session_state:
    st.session_state.agent = SoundCraftAgent()
    st.session_state.messages = [{"role": "assistant", "content": (
        "Hey there! Welcome to SoundCraft — I'm Jamie. "
        "Whether you're just picking up your first instrument or looking to upgrade your rig, "
        "I'm here to help you find exactly what you need.\n\nWhat brings you in today?"
    )}]
    st.session_state.handoff_data = None
    st.session_state.escalated = False

if "browse_results" not in st.session_state:
    st.session_state.browse_results = browse_products([], 5000)
if "browse_label" not in st.session_state:
    st.session_state.browse_label = "Browse Products"


# ── Two-column layout ─────────────────────────────────────────────────────────
chat_col, browse_col = st.columns([55, 45])

with chat_col:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🎵" if msg["role"] == "assistant" else "👤"):
            content = _safe_md(msg["content"]) if msg["role"] == "assistant" else msg["content"]
            st.markdown(content, unsafe_allow_html=msg["role"] == "assistant")
            if msg.get("product_ids"):
                render_product_cards(msg["product_ids"])

    if st.session_state.handoff_data:
        hd = st.session_state.handoff_data
        if st.session_state.escalated:
            st.markdown(f"""
            <div class="escalation-card">
                <div class="handoff-title" style="color:#2ecc71">&#10003; Connecting You to a Specialist</div>
                <strong>Reference:</strong> {hd.get('handoff_id', 'N/A')}<br>
                A SoundCraft Sales Engineer has been notified and will join shortly.<br>
                <small style="color:#888">They can see your full conversation — no need to repeat yourself.</small>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="handoff-card">
                <div class="handoff-title">&#9889; Sales Engineer Handoff Created</div>
                <strong>Handoff ID:</strong> {hd.get('handoff_id', 'N/A')}<br>
                <strong>Status:</strong> Routed to your dedicated SoundCraft Sales Engineer<br>
                <small style="color:#888">You'll receive a personal follow-up within 1 business hour.</small>
            </div>
            """, unsafe_allow_html=True)

with browse_col:
    if st.session_state.browse_label != "Browse Products":
        st.markdown(
            f'<div class="jamie-picks-banner">🎸 {st.session_state.browse_label}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.subheader("Browse Products")

    CATEGORIES = [
        "Electric Guitar", "Acoustic Guitar", "Bass Guitar", "Drum Kit",
        "Keyboard/Synth", "Microphone", "Amplifier", "Recording Gear",
        "Effects Pedal", "Accessory",
    ]
    selected_cats = st.multiselect(
        "Category", CATEGORIES, key="browse_cats_select", placeholder="All categories"
    )
    max_price = st.slider(
        "Max Price", 100, 5000, 2000, step=50, format="$%d", key="browse_price_slider"
    )

    if st.button("Browse", key="browse_btn", type="primary"):
        st.session_state.browse_results = browse_products(selected_cats, max_price)
        st.session_state.browse_label = "Browse Products"
        st.rerun()

    render_product_tiles(st.session_state.browse_results)


# ── Chat input (must be top-level, not inside a column) ──────────────────────
if prompt := st.chat_input("Tell Jamie what you're looking for..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Jamie is thinking..."):
        try:
            reply, handoff = st.session_state.agent.send(
                prompt, st.session_state.messages
            )
            if handoff:
                st.session_state.handoff_data = handoff
                escalation_keywords = [
                    "speak to a human", "talk to a person", "real person",
                    "sales engineer", "talk to someone", "human", "person",
                    "representative", "rep",
                ]
                st.session_state.escalated = any(
                    k in prompt.lower() for k in escalation_keywords
                )
        except Exception as e:
            reply = f"Sorry, I ran into a technical issue: {e}"
            handoff = None

    rec_ids = list(st.session_state.agent.last_recommended_ids) if hasattr(
        st.session_state.agent, "last_recommended_ids"
    ) else []

    msg_entry = {"role": "assistant", "content": reply}
    if rec_ids:
        seen = set()
        msg_entry["product_ids"] = [x for x in rec_ids if not (x in seen or seen.add(x))]
        jamie_products = fetch_products(msg_entry["product_ids"])
        if jamie_products:
            st.session_state.browse_results = jamie_products
            st.session_state.browse_label = "Jamie's Picks"

    st.session_state.messages.append(msg_entry)
    st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🧑‍💼 Sales Engineer View")
    st.caption("Live handoff queue")

    try:
        if DB_PATH.exists():
            con = duckdb.connect(str(DB_PATH), read_only=True)
            try:
                rows = con.execute("""
                    SELECT handoff_id, customer_name, priority, status, created_at,
                           conversation_summary
                    FROM agent_handoffs
                    ORDER BY created_at DESC
                    LIMIT 5
                """).fetchall()
                if rows:
                    for row in rows:
                        hid, name, priority, status, ts, summary = row
                        badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                        status_icon = "🆕" if status == "new" else "👤"
                        st.markdown(f"**{badge} {status_icon} {hid}** — {name}")
                        st.caption(summary[:120] + "..." if summary and len(summary) > 120 else summary)
                        st.divider()
                else:
                    st.info("No handoffs yet.")
            except Exception:
                st.info("No handoffs yet.")
            finally:
                con.close()
        else:
            st.info("Run `python scripts/seed_db.py` first.")
    except Exception as e:
        st.warning(f"Could not load handoffs: {e}")

    st.divider()
    st.page_link("pages/se_dashboard.py", label="Open SE Dashboard →", icon="🖥️")

    if st.button("🔄 Reset Conversation"):
        for key in ["agent", "messages", "handoff_data", "escalated",
                    "browse_results", "browse_label"]:
            st.session_state.pop(key, None)
        st.rerun()
