"""
Bootstraps DuckDB from raw CSVs and runs dbt transformations.
Run once before starting the Streamlit app.
"""
import os
import subprocess
import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "soundcraft.duckdb"
DATA_PATH = Path(__file__).parent.parent / "data" / "raw"
DBT_DIR = Path(__file__).parent.parent / "dbt"


def seed_raw_tables(con: duckdb.DuckDBPyConnection):
    print("Seeding raw tables...")
    for csv_file in DATA_PATH.glob("*.csv"):
        table_name = f"raw_{csv_file.stem}"
        con.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT * FROM read_csv_auto('{csv_file.as_posix()}')
        """)
        count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"  {table_name}: {count} rows")


def run_dbt():
    print("\nRunning dbt transformations...")
    env = os.environ.copy()
    env["SOUNDCRAFT_DB_PATH"] = str(DB_PATH)
    env["SOUNDCRAFT_DATA_PATH"] = str(DATA_PATH)

    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", "."],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("dbt error:", result.stderr)
    else:
        print("dbt models materialized successfully.")


if __name__ == "__main__":
    DB_PATH.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    seed_raw_tables(con)
    con.close()
    run_dbt()
    print(f"\nDatabase ready at: {DB_PATH}")
