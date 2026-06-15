"""
Resolves config values from Streamlit secrets (cloud) or .env (local).
"""
import os
from pathlib import Path


def get_secret(key: str) -> str:
    # Streamlit Cloud secrets take priority
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass

    # Fall back to environment / .env
    val = os.environ.get(key)
    if val:
        return val

    raise ValueError(
        f"Missing required config: '{key}'. "
        f"Set it in .streamlit/secrets.toml or .env"
    )
