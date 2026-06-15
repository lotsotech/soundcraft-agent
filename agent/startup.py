"""
Auto-seeds DuckDB on Streamlit Cloud where the db/ directory doesn't persist.
Import this at the top of app.py before anything else.
"""
import os
import subprocess
import sys
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data" / "raw"
DBT_DIR   = Path(__file__).parent.parent / "dbt"

# On Streamlit Cloud, write DB to /tmp (writable ephemeral storage)
# Locally, use db/ directory as normal
_repo_db = Path(__file__).parent.parent / "db" / "soundcraft.duckdb"
_tmp_db  = Path("/tmp/soundcraft.duckdb")


def get_db_path() -> Path:
    if _repo_db.parent.exists():
        return _repo_db
    return _tmp_db


def ensure_db():
    db_path = get_db_path()
    if db_path.exists():
        return  # Already seeded this session

    import duckdb
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Seed raw tables
    con = duckdb.connect(str(db_path))
    for csv_file in DATA_PATH.glob("*.csv"):
        table_name = f"raw_{csv_file.stem}"
        con.execute(f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT * FROM read_csv_auto('{csv_file.as_posix()}')
        """)
    con.close()

    # Run dbt
    env = os.environ.copy()
    env["SOUNDCRAFT_DB_PATH"] = str(db_path)
    env["SOUNDCRAFT_DATA_PATH"] = str(DATA_PATH)
    result = subprocess.run(
        [sys.executable, "-m", "dbt", "run", "--profiles-dir", "."],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"dbt seed failed:\n{result.stderr}")
