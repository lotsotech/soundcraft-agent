"""
SoundCraft SE Dashboard — internal Sales Engineer view
Live handoff queue with full transcript access and claim workflow.
"""
import json
from pathlib import Path

import duckdb
import streamlit as st

from agent.startup import ensure_db, get_db_path

ensure_db()
DB_PATH = get_db_path()

st.set_page_config(
    page_title="SoundCraft | SE Dashboard",
    page_icon="🧑‍💼",
    layout="wide",
)

st.markdown("""
<style>
    .priority-high   { color: #e74c3c; font-weight: 700; }
    .priority-medium { color: #f39c12; font-weight: 700; }
    .priority-low    { color: #2ecc71; font-weight: 700; }
    .new-badge {
        background: #e74c3c; color: white; border-radius: 6px;
        padding: 2px 8px; font-size: 0.75rem; font-weight: 700;
    }
    .claimed-badge {
        background: #3498db; color: white; border-radius: 6px;
        padding: 2px 8px; font-size: 0.75rem; font-weight: 700;
    }
    .transcript-bubble-customer {
        background: #2c3e50; border-radius: 12px 12px 12px 0;
        padding: 0.6rem 1rem; margin: 0.3rem 0; max-width: 80%;
    }
    .transcript-bubble-agent {
        background: #1a3a2a; border-radius: 12px 12px 0 12px;
        padding: 0.6rem 1rem; margin: 0.3rem 0 0.3rem auto; max-width: 80%;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image("assets/soundcraft_logo.png", width=180)
with col_title:
    st.markdown("## SE Dashboard")
    st.caption("Internal view — live customer handoff queue")

# SE identity selector (simulates login for demo purposes)
se_name = st.sidebar.selectbox(
    "You are logged in as:",
    ["Sarah Chen", "Mike Torres", "Alex Rivera", "Jordan Kim"],
)
st.sidebar.divider()
if st.sidebar.button("🔄 Refresh Now"):
    st.rerun()

# ── Load handoffs ─────────────────────────────────────────────────────────────
def load_handoffs():
    if not DB_PATH.exists():
        return []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT handoff_id, session_id, customer_name, skill_level,
                   primary_instrument, use_case, budget_range, existing_gear,
                   recommended_products, conversation_summary, priority,
                   status, claimed_by, claimed_at, created_at
            FROM agent_handoffs
            ORDER BY
                CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                created_at DESC
        """).fetchall()
        cols = ["handoff_id", "session_id", "customer_name", "skill_level",
                "primary_instrument", "use_case", "budget_range", "existing_gear",
                "recommended_products", "conversation_summary", "priority",
                "status", "claimed_by", "claimed_at", "created_at"]
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def load_transcript(session_id: str) -> list[dict]:
    if not DB_PATH.exists():
        return []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        row = con.execute(
            "SELECT messages FROM chat_transcripts WHERE session_id = ?",
            [session_id]
        ).fetchone()
        if row and row[0]:
            return json.loads(row[0])
        return []
    except Exception:
        return []
    finally:
        con.close()


def claim_handoff(handoff_id: str, se_name: str):
    con = duckdb.connect(str(DB_PATH))
    try:
        from datetime import datetime
        con.execute("""
            UPDATE agent_handoffs
            SET status = 'claimed', claimed_by = ?, claimed_at = ?
            WHERE handoff_id = ?
        """, [se_name, datetime.utcnow(), handoff_id])
    finally:
        con.close()


def close_handoff(handoff_id: str):
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("""
            UPDATE agent_handoffs SET status = 'closed' WHERE handoff_id = ?
        """, [handoff_id])
    finally:
        con.close()


# ── Metrics row ───────────────────────────────────────────────────────────────
handoffs = load_handoffs()

new_count    = sum(1 for h in handoffs if h["status"] == "new")
claimed_count = sum(1 for h in handoffs if h["status"] == "claimed")
high_count   = sum(1 for h in handoffs if h["priority"] == "high" and h["status"] == "new")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Handoffs", len(handoffs))
m2.metric("🆕 New", new_count, delta=f"+{high_count} urgent" if high_count else None,
          delta_color="inverse" if high_count else "off")
m3.metric("👤 In Progress", claimed_count)
m4.metric("✅ Closed", sum(1 for h in handoffs if h["status"] == "closed"))

st.divider()

# ── Handoff queue ─────────────────────────────────────────────────────────────
if not handoffs:
    st.info("No handoffs yet. Start a customer conversation to generate one.")
else:
    for h in handoffs:
        priority_color = {"high": "#e74c3c", "medium": "#f39c12", "low": "#2ecc71"}.get(h["priority"], "#888")
        priority_icon  = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(h["priority"], "⚪")
        status_label   = {"new": "🆕 NEW", "claimed": "👤 IN PROGRESS", "closed": "✅ CLOSED"}.get(h["status"], h["status"])

        with st.expander(
            f"{priority_icon} **{h['handoff_id']}** — {h['customer_name'] or 'Unknown'} "
            f"| {h['primary_instrument']} | {h['budget_range']} | {status_label}",
            expanded=(h["status"] == "new" and h["priority"] == "high"),
        ):
            left, right = st.columns([2, 3])

            with left:
                st.markdown("#### Customer Brief")
                st.markdown(f"**Name:** {h['customer_name'] or '—'}")
                st.markdown(f"**Skill Level:** {h['skill_level'] or '—'}")
                st.markdown(f"**Instrument:** {h['primary_instrument'] or '—'}")
                st.markdown(f"**Use Case:** {h['use_case'] or '—'}")
                st.markdown(f"**Budget:** {h['budget_range'] or '—'}")
                st.markdown(f"**Existing Gear:** {h['existing_gear'] or 'None mentioned'}")

                st.markdown("#### Jamie's Summary")
                st.info(h["conversation_summary"] or "No summary available.")

                try:
                    recs = json.loads(h["recommended_products"] or "[]")
                    if recs:
                        st.markdown(f"**Recommended Products:** {', '.join(recs)}")
                except Exception:
                    pass

                # Action buttons
                if h["status"] == "new":
                    if st.button(f"✋ Claim this lead", key=f"claim_{h['handoff_id']}"):
                        claim_handoff(h["handoff_id"], se_name)
                        st.success(f"Claimed by {se_name}")
                        st.rerun()
                elif h["status"] == "claimed":
                    st.markdown(f"**Claimed by:** {h['claimed_by']}")
                    if h["claimed_by"] == se_name:
                        if st.button(f"✅ Close handoff", key=f"close_{h['handoff_id']}"):
                            close_handoff(h["handoff_id"])
                            st.rerun()

            with right:
                st.markdown("#### Full Conversation Transcript")
                transcript = load_transcript(h["session_id"] or "")
                if transcript:
                    for msg in transcript:
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        if role == "user":
                            st.markdown(
                                f'<div class="transcript-bubble-customer">👤 {content}</div>',
                                unsafe_allow_html=True,
                            )
                        elif role == "assistant":
                            st.markdown(
                                f'<div class="transcript-bubble-agent">🎵 {content}</div>',
                                unsafe_allow_html=True,
                            )
                else:
                    st.caption("Transcript will appear here once a handoff is created during a live chat session.")

        st.markdown("")

