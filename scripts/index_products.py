"""
One-time script to embed all products and upsert into Pinecone.

Usage:
    python scripts/index_products.py

Requires PINECONE_API_KEY and GOOGLE_API_KEY in .env or environment.
Safe to re-run — upserts are idempotent.
"""
import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent.config import get_secret
from google import genai
from pinecone import Pinecone, ServerlessSpec

PRODUCTS_CSV = Path(__file__).parent.parent / "data" / "raw" / "products.csv"
INDEX_NAME   = "soundcraft-gear"
EMBED_MODEL  = "models/gemini-embedding-001"
EMBED_DIM    = 3072
BATCH_SIZE   = 50


def build_text(row: dict) -> str:
    parts = [
        row["name"],
        f"{row['brand']} {row['subcategory']}",
        row["description"],
        f"Skill level: {row['skill_level']}",
        f"Use case: {row['use_case']}",
        f"Category: {row['category']}",
    ]
    return ". ".join(p for p in parts if p.strip())


def main():
    pinecone_key = get_secret("PINECONE_API_KEY")
    google_key   = get_secret("GOOGLE_API_KEY")

    pc     = Pinecone(api_key=pinecone_key)
    client = genai.Client(api_key=google_key)

    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"Creating index '{INDEX_NAME}' ({EMBED_DIM}d cosine)...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print("Waiting for index to be ready...")
        time.sleep(15)
    else:
        print(f"Index '{INDEX_NAME}' already exists — upserting.")

    index = pc.Index(INDEX_NAME)

    with open(PRODUCTS_CSV, encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    print(f"Loaded {len(products)} products from {PRODUCTS_CSV.name}")

    total = 0
    for start in range(0, len(products), BATCH_SIZE):
        batch = products[start : start + BATCH_SIZE]
        texts = [build_text(p) for p in batch]

        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=texts,
        )
        vecs = [e.values for e in result.embeddings]

        vectors = [
            {
                "id": p["product_id"],
                "values": vec,
                "metadata": {
                    "product_id":  p["product_id"],
                    "name":        p["name"],
                    "brand":       p["brand"],
                    "category":    p["category"],
                    "price":       float(p["price"]),
                    "skill_level": p["skill_level"],
                    "use_case":    p["use_case"],
                    "type":        "product",
                },
            }
            for p, vec in zip(batch, vecs)
        ]

        index.upsert(vectors=vectors)
        total += len(vectors)
        print(f"  Upserted {total}/{len(products)}")
        time.sleep(0.5)

    print(f"\nDone. {total} products indexed in '{INDEX_NAME}'.")


if __name__ == "__main__":
    main()
