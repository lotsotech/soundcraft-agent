"""
SoundCraft First-Touch Agent — Streamlit Demo
"""
import streamlit as st
from agent.soundcraft_agent import SoundCraftAgent

st.set_page_config(
    page_title="SoundCraft | Find Your Sound",
    page_icon="🎸",
    layout="centered",
)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f0f0f; }
    .stChatMessage { border-radius: 12px; }
    .handoff-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #e85d04;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin-top: 1rem;
    }
    .handoff-title {
        color: #e85d04;
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🎸 SoundCraft")
    st.caption("Your personal gear advisor — powered by AI, backed by human experts")
with col2:
    st.image("https://img.icons8.com/fluency/96/guitar.png", width=72)

st.divider()

# ── Session state ─────────────────────────────────────────────────────────────
if "agent" not in st.session_state:
    st.session_state.agent = SoundCraftAgent()
    st.session_state.messages = []
    st.session_state.handoff_shown = False

    # Kick off with Jamie's opening line
    opening = (
        "Hey there! Welcome to SoundCraft — I'm Jamie. "
        "Whether you're just picking up your first instrument or looking to upgrade your rig, "
        "I'm here to help you find exactly what you need.\n\n"
        "What brings you in today?"
    )
    st.session_state.messages.append({"role": "assistant", "content": opening})

# ── Chat history ──────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🎵" if msg["role"] == "assistant" else "👤"):
        st.markdown(msg["content"])

# ── SE Handoff card ───────────────────────────────────────────────────────────
if st.session_state.get("handoff_data") and not st.session_state.handoff_shown:
    st.session_state.handoff_shown = True

if st.session_state.get("handoff_data"):
    hd = st.session_state.handoff_data
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
                reply, handoff = st.session_state.agent.send(prompt)
                if handoff:
                    st.session_state.handoff_data = handoff
            except Exception as e:
                reply = f"Sorry, I ran into a technical issue: {e}"
                handoff = None

        st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

    if st.session_state.get("handoff_data") and not st.session_state.handoff_shown:
        st.rerun()

# ── Sidebar: SE dashboard peek ────────────────────────────────────────────────
with st.sidebar:
    st.header("🧑‍💼 Sales Engineer View")
    st.caption("Live handoff queue — internal only")

    try:
        import duckdb
        from pathlib import Path
        db = Path(__file__).parent / "db" / "soundcraft.duckdb"
        if db.exists():
            con = duckdb.connect(str(db), read_only=True)
            try:
                rows = con.execute("""
                    SELECT handoff_id, customer_name, priority, created_at,
                           conversation_summary
                    FROM agent_handoffs
                    ORDER BY created_at DESC
                    LIMIT 5
                """).fetchall()
                if rows:
                    for row in rows:
                        hid, name, priority, ts, summary = row
                        badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                        st.markdown(f"**{badge} {hid}** — {name}")
                        st.caption(summary[:120] + "..." if len(summary) > 120 else summary)
                        st.divider()
                else:
                    st.info("No handoffs yet. Complete a chat to generate one.")
            except Exception:
                st.info("No handoffs yet.")
            finally:
                con.close()
        else:
            st.info("Run `python scripts/seed_db.py` first to initialize the database.")
    except Exception as e:
        st.warning(f"Could not load handoffs: {e}")

    st.divider()
    if st.button("🔄 Reset Conversation"):
        for key in ["agent", "messages", "handoff_data", "handoff_shown"]:
            st.session_state.pop(key, None)
        st.rerun()
