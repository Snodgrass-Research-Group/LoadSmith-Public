# data/ — Migrated Parquet Store

Produced by `python scripts/migrate_data.py` (one-time; decision D8).
Schema: docs/conversion_manual/HOOKS.md §3. LoadSmith reads ONLY this store
at runtime — never the raw .xls/.xlsx/.mat files in the region folders.

Regenerate any time from the raw archive; every parquet file's metadata
records its source path, SHA-256, and migration date.
