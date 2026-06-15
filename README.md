# SoundCraft First-Touch Agent

AI-powered first-touch sales advisor for a music gear retailer. Built with Gemini 2.0 Flash, DuckDB, dbt, and Streamlit.

## Architecture

```
Raw CSVs (products, customers, orders)
    ↓ Python seed script
DuckDB (local warehouse)
    ↓ dbt Core (staging → marts)
dim_products / dim_customers / fct_recommendations
    ↓ ChromaDB (product embeddings) [future]
Gemini 2.0 Flash Agent (function calling)
    → search_products tool
    → get_product_details tool
    → create_se_handoff tool
    ↓
Streamlit UI (customer chat + SE dashboard)
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your API key
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# 3. Seed the database and run dbt
python scripts/seed_db.py

# 4. Launch the app
streamlit run app.py
```

## Project Structure

```
soundcraft/
├── data/raw/           # Seed CSVs (products, customers, orders, handoffs)
├── db/                 # DuckDB database (git-ignored)
├── dbt/
│   ├── models/
│   │   ├── staging/    # stg_products, stg_customers, stg_orders
│   │   └── marts/      # dim_products, dim_customers, fct_recommendations
│   └── dbt_project.yml
├── agent/
│   └── soundcraft_agent.py   # Gemini agent with tool calling
├── scripts/
│   └── seed_db.py      # Bootstrap script
├── app.py              # Streamlit UI
└── requirements.txt
```

## Key Design Decisions

**DuckDB over Postgres/Snowflake**: Zero-infra for demo, full SQL semantics, production path is a config change to dbt profile.

**dbt staging → marts pattern**: Separates raw ingestion concerns from business logic. Lineage is auditable. Swap the source without touching downstream models.

**Gemini function calling over RAG**: Structured tool calls against a typed schema are more deterministic than freeform RAG for product lookup — critical when recommendations need to be defensible.

**SE Handoff as a first-class data artifact**: The agent doesn't just chat — it produces a structured record that enters the CRM workflow. The AI output is the data product.
