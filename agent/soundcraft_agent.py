"""
SoundCraft First-Touch Sales Agent
Powered by Gemini 2.5 Flash with function calling against DuckDB product catalog.
"""
import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
from google import genai
from google.genai import types
from agent.config import get_secret

_repo_db = Path(__file__).parent.parent / "db" / "soundcraft.duckdb"
_tmp_db  = Path("/tmp/soundcraft.duckdb")
DB_PATH  = _tmp_db if not _repo_db.parent.exists() else _repo_db

SYSTEM_PROMPT = """You are Jamie, a knowledgeable first-touch Sales Advisor at SoundCraft — a premier music gear retailer.

Your personality:
- Warm, conversational, and genuinely curious about the customer's musical journey
- Expert-level gear knowledge but never condescending — you meet customers where they are
- You ask ONE focused question at a time, like a real conversation
- You listen carefully and remember what the customer tells you

Your goal is to:
1. Understand the customer's musical situation (skill level, instrument, use case, budget)
2. Learn what gear they already own so you don't recommend duplicates
3. Recommend 2-3 specific products that genuinely fit their needs
4. Capture a warm, detailed handoff brief for the human Sales Engineer who will follow up

Key behaviors:
- Never ask more than one question at a time
- After 3-4 exchanges, you have enough to make a recommendation
- Always explain WHY you're recommending something — connect gear to their specific situation
- BUDGET: Honoring the customer's stated budget is non-negotiable. When a customer gives a price ("around $3500", "about $500", "my budget is $1200"), ALWAYS pass that exact number as target_price in search_products — do NOT omit it. The search ranks results by proximity to that price, so without target_price you will return the cheapest items in the catalog, not the ones that match the customer's budget. Never recommend products far below the customer's stated budget without explicitly asking if they want a more affordable option.
- CATALOG SCOPE: SoundCraft specializes in guitars, bass, drums, keys, microphones, amplifiers, recording gear, effects pedals, and accessories. If a customer asks about something outside this catalog (violins, orchestral instruments, brass, woodwinds, etc.), be upfront and warm: "That's actually outside our specialty at SoundCraft — we focus on guitars, keys, drums, and recording gear. For that I'd point you toward a dedicated orchestral shop." Do NOT pretend it is a search tool failure.
- If a search returns empty results, retry with a broader category term before giving up (e.g. try "Guitar" if "Acoustic Guitar beginner" returns nothing). Never tell the customer the search tool is broken or having technical issues.
- When you have enough context to make recommendations, call create_se_handoff to log the session
- ESCALATION: If the customer explicitly asks to speak to a human, talk to a person, or requests a Sales Engineer at any point, you MUST immediately call create_se_handoff with priority="high" and tell the customer warmly that a specialist is on their way. Do not keep chatting — trigger the handoff right away.

You represent SoundCraft's brand promise: the knowledgeable friend in the room, not a chatbot."""


# ── JSON encoder ──────────────────────────────────────────────────────────────

class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


# ── Tool implementations ───────────────────────────────────────────────────────

def search_products(
    category: str = None,
    skill_level: str = None,
    max_price: float = None,
    min_price: float = None,
    target_price: float = None,
    use_case: str = None,
    brand: str = None,
) -> list[dict]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        conditions = ["in_stock = true"]
        params = []
        if category:
            conditions.append("(lower(category) LIKE lower(?) OR lower(subcategory) LIKE lower(?))")
            params.extend([f"%{category}%", f"%{category}%"])
        if skill_level:
            conditions.append("lower(skill_level) LIKE lower(?)")
            params.append(f"%{skill_level}%")
        if max_price is not None:
            conditions.append("price <= ?")
            params.append(max_price)
        if min_price is not None:
            conditions.append("price >= ?")
            params.append(min_price)
        if use_case:
            conditions.append("lower(use_case) LIKE lower(?)")
            params.append(f"%{use_case}%")
        if brand:
            conditions.append("lower(brand) LIKE lower(?)")
            params.append(f"%{brand}%")

        where = " AND ".join(conditions)
        # Sort by proximity to target_price when given; otherwise cheapest first
        if target_price is not None:
            order_clause = f"ABS(price - {float(target_price)})"
        else:
            order_clause = "price ASC"
        rows = con.execute(f"""
            SELECT product_id, product_name, brand, subcategory,
                   price, skill_level, use_case, price_tier
            FROM main.dim_products
            WHERE {where}
            ORDER BY {order_clause}
            LIMIT 5
        """, params).fetchall()
        cols = ["product_id", "product_name", "brand", "subcategory",
                "price", "skill_level", "use_case", "price_tier"]
        return [{k: float(v) if isinstance(v, Decimal) else v for k, v in zip(cols, row)}
                for row in rows]
    finally:
        con.close()


def get_product_details(product_id: str) -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        row = con.execute("""
            SELECT product_id, product_name, brand, category, subcategory,
                   price, description, skill_level, use_case, price_tier,
                   in_stock, manufacturer_url
            FROM main.dim_products WHERE product_id = ?
        """, [product_id]).fetchone()
        if not row:
            return {"error": f"Product {product_id} not found"}
        cols = ["product_id", "product_name", "brand", "category", "subcategory",
                "price", "description", "skill_level", "use_case", "price_tier",
                "in_stock", "manufacturer_url"]
        return {k: float(v) if isinstance(v, Decimal) else v for k, v in zip(cols, row)}
    finally:
        con.close()


def create_se_handoff(
    customer_name: str,
    skill_level: str,
    primary_instrument: str,
    use_case: str,
    budget_range: str,
    existing_gear: str,
    recommended_product_ids: list[str],
    conversation_summary: str,
    priority: str = "medium",
) -> dict:
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS agent_handoffs (
                handoff_id           VARCHAR PRIMARY KEY,
                session_id           VARCHAR,
                customer_name        VARCHAR,
                skill_level          VARCHAR,
                primary_instrument   VARCHAR,
                use_case             VARCHAR,
                budget_range         VARCHAR,
                existing_gear        VARCHAR,
                recommended_products JSON,
                conversation_summary VARCHAR,
                priority             VARCHAR,
                status               VARCHAR DEFAULT 'new',
                claimed_by           VARCHAR,
                claimed_at           TIMESTAMP,
                created_at           TIMESTAMP
            )
        """)
        handoff_id = f"H-{uuid.uuid4().hex[:8].upper()}"
        session_id = f"S-{uuid.uuid4().hex[:8].upper()}"
        con.execute("""
            INSERT INTO agent_handoffs
            (handoff_id, session_id, customer_name, skill_level, primary_instrument,
             use_case, budget_range, existing_gear, recommended_products,
             conversation_summary, priority, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'new',?)
        """, [handoff_id, session_id, customer_name, skill_level, primary_instrument,
              use_case, budget_range, existing_gear,
              json.dumps(recommended_product_ids), conversation_summary,
              priority, datetime.utcnow()])
        return {"status": "success", "handoff_id": handoff_id, "session_id": session_id,
                "message": f"Handoff {handoff_id} logged and routed to a SoundCraft Sales Engineer."}
    finally:
        con.close()


def save_transcript(session_id: str, messages: list[dict]):
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS chat_transcripts (
                session_id  VARCHAR PRIMARY KEY,
                messages    JSON,
                updated_at  TIMESTAMP
            )
        """)
        con.execute("""
            INSERT INTO chat_transcripts VALUES (?, ?, ?)
            ON CONFLICT (session_id) DO UPDATE SET
                messages = excluded.messages,
                updated_at = excluded.updated_at
        """, [session_id, json.dumps(messages, cls=_SafeEncoder), datetime.utcnow()])
    finally:
        con.close()


# ── Tool schemas for google-genai SDK ─────────────────────────────────────────

TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="search_products",
            description="Search the SoundCraft product catalog. Use this to find products matching customer needs.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "category":     types.Schema(type=types.Type.STRING, description="Product category or subcategory e.g. Guitar, Acoustic Guitar, Electric Guitar, Bass Guitar, Amplifier, Drums, Keys, Microphones, Recording, Pedals, Accessories"),
                    "skill_level":  types.Schema(type=types.Type.STRING, description="Customer skill level: beginner, intermediate, advanced"),
                    "max_price":    types.Schema(type=types.Type.NUMBER, description="Hard upper price limit in USD. Only set when customer says 'under X' or 'no more than X'."),
                    "min_price":    types.Schema(type=types.Type.NUMBER, description="Hard lower price limit in USD."),
                    "target_price": types.Schema(type=types.Type.NUMBER, description="The customer's stated budget or 'around X' price. Results are sorted by closest match to this price. ALWAYS set this when the customer gives a budget or price point."),
                    "use_case":     types.Schema(type=types.Type.STRING, description="Use case: practice, live performance, studio recording, home studio"),
                    "brand":        types.Schema(type=types.Type.STRING, description="Specific brand name"),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="get_product_details",
            description="Get full details for a specific product by its ID.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product_id": types.Schema(type=types.Type.STRING, description="The product ID e.g. P0001"),
                },
                required=["product_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="create_se_handoff",
            description="Log this customer session as a Sales Engineer handoff. Call this after making recommendations OR immediately if customer requests a human.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "customer_name":           types.Schema(type=types.Type.STRING),
                    "skill_level":             types.Schema(type=types.Type.STRING),
                    "primary_instrument":      types.Schema(type=types.Type.STRING),
                    "use_case":                types.Schema(type=types.Type.STRING),
                    "budget_range":            types.Schema(type=types.Type.STRING),
                    "existing_gear":           types.Schema(type=types.Type.STRING, description="Gear the customer already owns"),
                    "recommended_product_ids": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                    "conversation_summary":    types.Schema(type=types.Type.STRING, description="2-3 sentence warm summary for the SE"),
                    "priority":                types.Schema(type=types.Type.STRING, description="Use high if customer explicitly requested a human"),
                },
                required=["customer_name", "skill_level", "primary_instrument", "use_case",
                          "budget_range", "existing_gear", "recommended_product_ids",
                          "conversation_summary"],
            ),
        ),
    ])
]

TOOL_DISPATCH: dict[str, Any] = {
    "search_products":     search_products,
    "get_product_details": get_product_details,
    "create_se_handoff":   create_se_handoff,
}


# ── Agent session ──────────────────────────────────────────────────────────────

class SoundCraftAgent:
    def __init__(self):
        api_key = get_secret("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.history: list[types.Content] = []
        self.handoff_logged = False
        self.session_id: str | None = None
        self.last_recommended_ids: list[str] = []

    def send(self, user_message: str, transcript: list[dict]) -> tuple[str, dict | None]:
        self.history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
        handoff_result = None

        while True:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=TOOLS,
                    http_options=types.HttpOptions(timeout=30000),
                ),
            )

            self.history.append(response.candidates[0].content)

            # Check for function calls
            tool_calls = [
                p for p in response.candidates[0].content.parts
                if p.function_call is not None
            ]

            if not tool_calls:
                text = "".join(
                    p.text for p in response.candidates[0].content.parts
                    if hasattr(p, "text") and p.text
                )
                if self.session_id:
                    save_transcript(self.session_id, transcript)
                return text.strip(), handoff_result

            # Execute tool calls and collect results
            result_parts = []
            for part in tool_calls:
                fn_name = part.function_call.name
                fn_args = dict(part.function_call.args)
                fn = TOOL_DISPATCH.get(fn_name)

                if fn:
                    result = fn(**fn_args)
                    if fn_name == "create_se_handoff" and result.get("status") == "success":
                        handoff_result = result
                        self.handoff_logged = True
                        self.session_id = result.get("session_id")
                        self.last_recommended_ids = fn_args.get("recommended_product_ids", [])
                        save_transcript(self.session_id, transcript)
                    elif fn_name == "search_products" and isinstance(result, list):
                        self.last_recommended_ids = [r["product_id"] for r in result]
                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                result_parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fn_name,
                        response={"result": json.dumps(result, cls=_SafeEncoder)},
                    )
                ))

            self.history.append(types.Content(role="user", parts=result_parts))
