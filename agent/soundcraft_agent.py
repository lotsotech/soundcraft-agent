"""
SoundCraft First-Touch Sales Agent
Powered by Gemini 2.0 Flash with function calling against DuckDB product catalog.
"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import google.generativeai as genai

DB_PATH = Path(__file__).parent.parent / "db" / "soundcraft.duckdb"

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
- Be honest about limitations: "That's a great question — let me get you connected with one of our specialists who can go deeper on that"
- When you have enough context, call create_se_handoff to log the session

You represent SoundCraft's brand promise: the knowledgeable friend in the room, not a chatbot."""


# ── Tool definitions for Gemini function calling ──────────────────────────────

def search_products(
    category: str = None,
    skill_level: str = None,
    max_price: float = None,
    min_price: float = None,
    use_case: str = None,
    brand: str = None,
) -> list[dict]:
    """Search the SoundCraft product catalog with filters."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        conditions = ["in_stock = true"]
        params = []

        if category:
            conditions.append("lower(category) LIKE lower(?)")
            params.append(f"%{category}%")
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
        query = f"""
            SELECT product_id, product_name, brand, category, subcategory,
                   price, description, skill_level, use_case, price_tier
            FROM main.dim_products
            WHERE {where}
            ORDER BY price ASC
            LIMIT 10
        """
        rows = con.execute(query, params).fetchall()
        cols = ["product_id", "product_name", "brand", "category", "subcategory",
                "price", "description", "skill_level", "use_case", "price_tier"]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        con.close()


def get_product_details(product_id: str) -> dict:
    """Get full details for a specific product by ID."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        row = con.execute(
            """SELECT product_id, product_name, brand, category, subcategory,
                      price, description, skill_level, use_case, price_tier, in_stock
               FROM main.dim_products WHERE product_id = ?""",
            [product_id],
        ).fetchone()
        if not row:
            return {"error": f"Product {product_id} not found"}
        cols = ["product_id", "product_name", "brand", "category", "subcategory",
                "price", "description", "skill_level", "use_case", "price_tier", "in_stock"]
        return dict(zip(cols, row))
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
    """
    Log a completed session as a Sales Engineer handoff record.
    Call this once you have enough context and have made recommendations.
    """
    con = duckdb.connect(str(DB_PATH))
    try:
        # Ensure handoff table exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS agent_handoffs (
                handoff_id      VARCHAR PRIMARY KEY,
                session_id      VARCHAR,
                customer_name   VARCHAR,
                skill_level     VARCHAR,
                primary_instrument VARCHAR,
                use_case        VARCHAR,
                budget_range    VARCHAR,
                existing_gear   VARCHAR,
                recommended_products JSON,
                conversation_summary VARCHAR,
                priority        VARCHAR,
                created_at      TIMESTAMP
            )
        """)

        handoff_id = f"H-{uuid.uuid4().hex[:8].upper()}"
        session_id = f"S-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.utcnow()

        con.execute(
            """INSERT INTO agent_handoffs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                handoff_id, session_id, customer_name, skill_level,
                primary_instrument, use_case, budget_range, existing_gear,
                json.dumps(recommended_product_ids), conversation_summary,
                priority, now,
            ],
        )
        return {
            "status": "success",
            "handoff_id": handoff_id,
            "message": f"Handoff {handoff_id} logged and routed to a SoundCraft Sales Engineer.",
        }
    finally:
        con.close()


# ── Tool schema declarations for Gemini ───────────────────────────────────────

TOOLS = [
    {
        "function_declarations": [
            {
                "name": "search_products",
                "description": "Search the SoundCraft product catalog. Use this to find products matching customer needs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category":    {"type": "string", "description": "Product category e.g. Guitar, Amplifier, Drums, Keys, Microphones, Recording, Accessories"},
                        "skill_level": {"type": "string", "description": "Customer skill level: beginner, intermediate, advanced"},
                        "max_price":   {"type": "number", "description": "Maximum price in USD"},
                        "min_price":   {"type": "number", "description": "Minimum price in USD"},
                        "use_case":    {"type": "string", "description": "Use case: practice, live performance, studio recording, home studio"},
                        "brand":       {"type": "string", "description": "Specific brand name"},
                    },
                },
            },
            {
                "name": "get_product_details",
                "description": "Get full details for a specific product by its ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "description": "The product ID e.g. P001"},
                    },
                    "required": ["product_id"],
                },
            },
            {
                "name": "create_se_handoff",
                "description": "Log this customer session as a Sales Engineer handoff. Call this after making recommendations to create a warm lead record.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_name":           {"type": "string"},
                        "skill_level":             {"type": "string"},
                        "primary_instrument":      {"type": "string"},
                        "use_case":                {"type": "string"},
                        "budget_range":            {"type": "string"},
                        "existing_gear":           {"type": "string", "description": "Gear the customer already owns"},
                        "recommended_product_ids": {"type": "array", "items": {"type": "string"}},
                        "conversation_summary":    {"type": "string", "description": "2-3 sentence warm summary for the SE"},
                        "priority":                {"type": "string", "enum": ["low", "medium", "high"], "description": "Lead priority based on budget and purchase intent"},
                    },
                    "required": [
                        "customer_name", "skill_level", "primary_instrument",
                        "use_case", "budget_range", "existing_gear",
                        "recommended_product_ids", "conversation_summary",
                    ],
                },
            },
        ]
    }
]

TOOL_DISPATCH: dict[str, Any] = {
    "search_products":   search_products,
    "get_product_details": get_product_details,
    "create_se_handoff": create_se_handoff,
}


# ── Agent session ──────────────────────────────────────────────────────────────

class SoundCraftAgent:
    def __init__(self):
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT,
            tools=TOOLS,
        )
        self.chat = self.model.start_chat(history=[])
        self.handoff_logged = False

    def send(self, user_message: str) -> tuple[str, dict | None]:
        """
        Send a message and handle any tool calls.
        Returns (assistant_text, handoff_record_or_None).
        """
        response = self.chat.send_message(user_message)
        handoff_result = None

        # Agentic loop: keep processing tool calls until we get a text response
        while True:
            candidate = response.candidates[0]

            # Check for function calls in the response parts
            tool_calls = [
                part for part in candidate.content.parts
                if hasattr(part, "function_call") and part.function_call.name
            ]

            if not tool_calls:
                # Pure text response — we're done
                text = "".join(
                    part.text for part in candidate.content.parts
                    if hasattr(part, "text")
                )
                return text.strip(), handoff_result

            # Execute all tool calls and collect results
            tool_results = []
            for part in tool_calls:
                fn_name = part.function_call.name
                fn_args = dict(part.function_call.args)
                fn = TOOL_DISPATCH.get(fn_name)

                if fn:
                    result = fn(**fn_args)
                    if fn_name == "create_se_handoff" and result.get("status") == "success":
                        handoff_result = result
                        self.handoff_logged = True
                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                tool_results.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn_name,
                            response={"result": json.dumps(result)},
                        )
                    )
                )

            # Feed tool results back to the model
            response = self.chat.send_message(tool_results)
