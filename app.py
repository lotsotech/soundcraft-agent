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
    layout="centered",
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
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.image("assets/soundcraft_logo.png", width=320)
st.caption("Your personal gear advisor — powered by AI, backed by human experts")
st.divider()


# ── Product card renderer ─────────────────────────────────────────────────────

def fetch_products(product_ids: list[str]) -> list[dict]:
    if not DB_PATH.exists() or not product_ids:
        return []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        placeholders = ",".join(["?"] * len(product_ids))
        rows = con.execute(
            f"""SELECT product_id, product_name, brand, category, price,
                       description, skill_level, use_case, price_tier, manufacturer_url
                FROM main.dim_products WHERE product_id IN ({placeholders})""",
            product_ids,
        ).fetchall()
        cols = ["product_id", "product_name", "brand", "category", "price",
                "description", "skill_level", "use_case", "price_tier", "manufacturer_url"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def render_product_cards(product_ids: list[str]):
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


# ── Session state ─────────────────────────────────────────────────────────────
if "agent" not in st.session_state:
    st.session_state.agent = SoundCraftAgent()
    st.session_state.messages = []
    st.session_state.handoff_data = None
    st.session_state.escalated = False
    st.session_state.recommended_ids = []

    opening = (
        "Hey there! Welcome to SoundCraft — I'm Jamie. "
        "Whether you're just picking up your first instrument or looking to upgrade your rig, "
        "I'm here to help you find exactly what you need.\n\n"
        "What brings you in today?"
    )
    st.session_state.messages.append({"role": "assistant", "content": opening})

# ── Chat history ──────────────────────────────────────────────────────────────
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🎵" if msg["role"] == "assistant" else "👤"):
        st.markdown(msg["content"])
        # Render product cards attached to this message
        if msg.get("product_ids"):
            render_product_cards(msg["product_ids"])

# ── Handoff / escalation card ─────────────────────────────────────────────────
if st.session_state.handoff_data:
    hd = st.session_state.handoff_data
    if st.session_state.escalated:
        st.markdown(f"""
        <div class="escalation-card">
            <div class="handoff-title" style="color:#2ecc71">✅ Connecting You to a Specialist</div>
            <strong>Reference:</strong> {hd.get('handoff_id', 'N/A')}<br>
            A SoundCraft Sales Engineer has been notified and will join shortly.<br>
            <small style="color:#888">They can see your full conversation — no need to repeat yourself.</small>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="handoff-card">
            <div class="handoff-title">⚡ Sales Engineer Handoff Created</div>
            <strong>Handoff ID:</strong> {hd.get('handoff_id', 'N/A')}<br>
            <strong>Status:</strong> Routed to your dedicated SoundCraft Sales Engineer<br>
            <small style="color:#888">You'll receive a personal follow-up within 1 business hour.</small>
        </div>
        """, unsafe_allow_html=True)

# ── Input ─────────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Tell Jamie what you're looking for..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🎵"):
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
                    # Attach recommended product IDs to this message for card rendering
                    rec_ids = handoff.get("recommended_product_ids", [])
                    if not rec_ids:
                        # Parse from the agent's tool call history if available
                        rec_ids = st.session_state.recommended_ids
            except Exception as e:
                reply = f"Sorry, I ran into a technical issue: {e}"
                handoff = None
                rec_ids = []

        st.markdown(reply)

        # Extract any product IDs mentioned in the reply for card rendering
        rec_ids = st.session_state.agent.last_recommended_ids if hasattr(
            st.session_state.agent, "last_recommended_ids"
        ) else []

        msg_entry = {"role": "assistant", "content": reply}
        if rec_ids:
            msg_entry["product_ids"] = rec_ids
            render_product_cards(rec_ids)

        st.session_state.messages.append(msg_entry)

    if st.session_state.handoff_data:
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
        for key in ["agent", "messages", "handoff_data", "escalated", "recommended_ids"]:
            st.session_state.pop(key, None)
        st.rerun()
