"""
Auto-seeds DuckDB on startup. On Streamlit Cloud, runs pure DuckDB SQL
instead of dbt to avoid the heavy dbt dependency at runtime.
Locally, dbt is still used via scripts/seed_db.py.
"""
try:
    import fcntl as _fcntl
    def _lock(fh): _fcntl.flock(fh, _fcntl.LOCK_EX)
except ImportError:
    # Windows — no concurrent Streamlit workers, so no-op is safe locally
    def _lock(fh): pass

from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "raw"

_repo_db   = Path(__file__).parent.parent / "db" / "soundcraft.duckdb"
_tmp_db    = Path("/tmp/soundcraft.duckdb")
_lock_file = Path("/tmp/soundcraft.lock")


def get_db_path() -> Path:
    if _repo_db.parent.exists():
        return _repo_db
    return _tmp_db


def ensure_db():
    db_path = get_db_path()
    if db_path.exists():
        return

    # File lock prevents concurrent Streamlit threads from both seeding
    with open(_lock_file, "w") as lf:
        _lock(lf)
        if db_path.exists():  # re-check after acquiring lock
            return

        import duckdb
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(db_path))

        # ── Raw tables ────────────────────────────────────────────────────────
        for csv_file in sorted(DATA_PATH.glob("*.csv")):
            con.execute(f"""
                CREATE OR REPLACE TABLE raw_{csv_file.stem} AS
                SELECT * FROM read_csv_auto('{csv_file.as_posix()}')
            """)

        # ── Staging views ─────────────────────────────────────────────────────
        con.execute("""
            CREATE OR REPLACE VIEW stg_products AS
            SELECT
                product_id,
                name                            AS product_name,
                brand,
                category,
                subcategory,
                CAST(price AS DECIMAL(10,2))    AS price,
                description,
                skill_level,
                use_case,
                CAST(in_stock AS BOOLEAN)       AS in_stock,
                manufacturer_url
            FROM raw_products
        """)

        con.execute("""
            CREATE OR REPLACE VIEW stg_customers AS
            SELECT
                customer_id,
                first_name,
                last_name,
                first_name || ' ' || last_name  AS full_name,
                email,
                skill_level,
                primary_instrument,
                CAST(years_playing AS INTEGER)  AS years_playing,
                use_case,
                budget_range,
                CAST(created_at AS DATE)        AS created_at
            FROM raw_customers
        """)

        con.execute("""
            CREATE OR REPLACE VIEW stg_orders AS
            SELECT
                order_id,
                customer_id,
                product_id,
                CAST(quantity AS INTEGER)           AS quantity,
                CAST(unit_price AS DECIMAL(10,2))   AS unit_price,
                quantity * unit_price               AS line_total,
                CAST(order_date AS DATE)            AS order_date,
                status
            FROM raw_orders
        """)

        # ── Mart tables ───────────────────────────────────────────────────────
        con.execute("""
            CREATE OR REPLACE TABLE dim_products AS
            WITH deduped AS (
                SELECT *
                FROM stg_products
                QUALIFY ROW_NUMBER() OVER (PARTITION BY product_name, price ORDER BY product_id) = 1
            )
            SELECT
                product_id,
                product_name,
                brand,
                category,
                subcategory,
                price,
                description,
                skill_level,
                use_case,
                in_stock,
                CASE
                    WHEN price < 100   THEN 'budget'
                    WHEN price < 500   THEN 'entry'
                    WHEN price < 1500  THEN 'mid-range'
                    ELSE                    'premium'
                END                             AS price_tier,
                string_split(skill_level, '-')  AS skill_levels_array,
                manufacturer_url
            FROM deduped
        """)

        con.execute("""
            CREATE OR REPLACE TABLE dim_customers AS
            WITH order_stats AS (
                SELECT
                    customer_id,
                    COUNT(DISTINCT order_id)        AS total_orders,
                    SUM(line_total)                 AS lifetime_value,
                    MAX(order_date)                 AS last_order_date,
                    MIN(order_date)                 AS first_order_date,
                    array_agg(DISTINCT product_id)  AS purchased_product_ids
                FROM stg_orders
                GROUP BY customer_id
            )
            SELECT
                c.customer_id,
                c.full_name,
                c.email,
                c.skill_level,
                c.primary_instrument,
                c.years_playing,
                c.use_case,
                c.budget_range,
                c.created_at,
                COALESCE(s.total_orders, 0)           AS total_orders,
                COALESCE(s.lifetime_value, 0)         AS lifetime_value,
                s.last_order_date,
                s.first_order_date,
                COALESCE(s.purchased_product_ids, []) AS purchased_product_ids
            FROM stg_customers c
            LEFT JOIN order_stats s USING (customer_id)
        """)

        con.execute("""
            CREATE OR REPLACE TABLE fct_recommendations AS
            SELECT
                handoff_id,
                session_id,
                customer_snapshot,
                recommended_products,
                conversation_summary,
                priority,
                CAST(created_at AS TIMESTAMP) AS created_at,
                assigned_se
            FROM raw_se_handoffs
        """)

        con.close()
