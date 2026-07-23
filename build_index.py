"""
build_index.py
----------------
One-time/repeatable script to (re)build the knowledge base index.

Run this whenever documents in knowledge/ change:
    python build_index.py
"""

from knowledge_base.indexer import build_index

count = build_index()
print(f"Indexed {count} chunks from knowledge/")