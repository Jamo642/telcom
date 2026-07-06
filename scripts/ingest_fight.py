#!/usr/bin/env python3
"""
scripts/ingest_fight.py

One-time script: embeds MITRE FiGHT techniques from data/fight_techniques.json
into the existing ChromaDB collection (telecom_incidents), tagged with
source="mitre_fight" so they're distinguishable from incidents/logs/manuals.

Run once (or after updating fight_techniques.json):
    python3 scripts/ingest_fight.py

Safe to re-run — uses upsert so duplicates are overwritten, not duplicated.
"""

import json
import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

CHROMA_PATH = os.environ.get("CHROMA_DB_PATH", "data/chroma_db")
FIGHT_JSON  = os.environ.get("FIGHT_JSON", "data/fight_techniques.json")
COLLECTION  = "telecom_incidents"


def main():
    # Load FiGHT techniques
    fight_path = Path(FIGHT_JSON)
    if not fight_path.exists():
        print(f"ERROR: {FIGHT_JSON} not found. Generate it first.", file=sys.stderr)
        sys.exit(1)

    with open(fight_path) as f:
        techniques: dict = json.load(f)

    print(f"Loaded {len(techniques)} FiGHT techniques from {FIGHT_JSON}")

    # Connect to ChromaDB
    import chromadb
    from services.embedding_service import get_embedding_service

    chroma_path = str(Path(CHROMA_PATH))
    client = chromadb.PersistentClient(path=chroma_path)
    try:
        col = client.get_collection(COLLECTION)
    except Exception:
        col = client.create_collection(COLLECTION, metadata={"hnsw:space": "l2"})

    print(f"ChromaDB collection '{COLLECTION}' has {col.count()} existing docs")

    emb_svc = get_embedding_service()

    docs, metas, ids, embeddings = [], [], [], []

    for tid, tech in techniques.items():
        # Build the text we embed: description + detection + mitigation
        text = (
            f"MITRE FiGHT Technique {tid}: {tech['name']}\n"
            f"Tactic: {tech['tactic']}\n"
            f"Description: {tech['description']}\n"
            f"Indicators: {'; '.join(tech['indicators'])}\n"
            f"Detection: {tech['detection_guidance']}\n"
            f"Mitigation: {tech['mitigation_guidance']}"
        )
        vec = emb_svc.embed_text(text).tolist()

        docs.append(text)
        ids.append(f"fight_{tid}")
        metas.append({
            "source":        "mitre_fight",
            "technique_id":  tid,
            "name":          tech["name"],
            "tactic":        tech["tactic"],
            "kill_chain":    tech.get("kill_chain_phase", ""),
        })
        embeddings.append(vec)

    # Upsert (add or overwrite)
    col.upsert(
        ids=ids,
        documents=docs,
        metadatas=metas,
        embeddings=embeddings,
    )

    print(f"Upserted {len(docs)} FiGHT technique documents into ChromaDB")
    print(f"Collection now has {col.count()} total docs")
    print()
    print("Verification — querying 'SS7 location tracking route interception':")
    q = emb_svc.embed_text("SS7 location tracking route interception").tolist()
    hits = col.query(
        query_embeddings=[q], n_results=3,
        where={"source": "mitre_fight"},
        include=["documents", "metadatas", "distances"],
    )
    for doc, meta, dist in zip(
        hits["documents"][0], hits["metadatas"][0], hits["distances"][0]
    ):
        print(f"  similarity={1-dist:.3f}  id={meta['technique_id']}  name={meta['name']}")


if __name__ == "__main__":
    main()
