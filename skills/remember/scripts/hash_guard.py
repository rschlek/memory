#!/usr/bin/env python3
"""Content-hash guard against a literal re-remember of the same source.

The `remember` skill calls this before ingesting so the same document does not get
captured twice. It keeps a tiny append-only ledger of content hashes.

Where the ledger lives:
  MEMORY_LEDGER_PATH            the ledger file, when set
  $MEMORY_HOME/memory-ledger.jsonl   otherwise, when MEMORY_HOME is set
  ~/.agent-memory/memory-ledger.jsonl   otherwise

New records go only to that ledger. Reads also take in, without changing them, any
`memory-ledger.jsonl` in a hidden folder directly under the home folder
(~/.<folder>/memory-ledger.jsonl), where earlier versions of this guard kept it,
so a source recorded there is still recognized.

Usage:
  # Check whether a source has already been remembered:
  python hash_guard.py check --text-file extracted.txt
  python hash_guard.py check --file image.png          # hash raw bytes (images/binaries)
  echo "pasted text" | python hash_guard.py check       # hash stdin

  # After a CONFIRMED ingest (the capture landed, not merely accepted), record it
  # so future re-remembers are caught:
  python hash_guard.py record --text-file extracted.txt --name "Planning meeting"

Output is a single JSON line: {"duplicate": bool, "hash": "...", "existing": {...}|null}.
On `check`, exit code is 0 (clean) or 3 (duplicate found) so the skill can branch.
`record` never blocks; it always exits 0.

Hash the NORMALIZED extracted text for documents/transcripts (so a re-export of the
same content is still caught), or raw file bytes for images/binaries via --file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

LEDGER_NAME = "memory-ledger.jsonl"


def memory_home() -> Path:
    return Path(os.environ.get("MEMORY_HOME") or Path.home() / ".agent-memory").expanduser()


LEDGER = Path(os.environ.get("MEMORY_LEDGER_PATH") or memory_home() / LEDGER_NAME).expanduser()


def legacy_ledgers() -> List[Path]:
    """Ledgers an earlier version left in ~/.<folder>/, read-only."""
    try:
        found = sorted(Path.home().glob(".*/" + LEDGER_NAME))
    except OSError:
        return []
    primary = _key(LEDGER)
    return [p for p in found if p.is_file() and _key(p) != primary]


def _key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def normalize(text: str) -> str:
    """Collapse whitespace and normalize line endings so trivial reformatting of the
    same content still hashes identically. Intentionally conservative: this catches a
    literal re-remember, not a paraphrase."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def read_input(args) -> Tuple[str, None]:
    """Return (hash_hex, None). Reads --text-file, --file (raw bytes), or stdin."""
    if args.file:
        data = Path(args.file).read_bytes()
        return hashlib.sha256(data).hexdigest(), None
    if args.text_file:
        raw = Path(args.text_file).read_text(encoding="utf-8", errors="replace")
    else:
        raw = sys.stdin.read()
    return hashlib.sha256(normalize(raw).encode("utf-8")).hexdigest(), None


def _read(path: Path) -> List[dict]:
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def load_ledger() -> List[dict]:
    """Every record: the ledger first, then any legacy ledgers."""
    out = _read(LEDGER) if LEDGER.exists() else []
    for path in legacy_ledgers():
        for rec in _read(path):
            rec.setdefault("ledger", str(path))
            out.append(rec)
    return out


def find(hash_hex: str) -> Optional[dict]:
    for rec in load_ledger():
        if rec.get("hash") == hash_hex:
            return rec
    return None


def append(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_check(args) -> int:
    hash_hex, _ = read_input(args)
    existing = find(hash_hex)
    print(json.dumps({
        "duplicate": existing is not None,
        "hash": hash_hex,
        "existing": existing,
    }))
    return 3 if existing else 0


def cmd_record(args) -> int:
    hash_hex, _ = read_input(args)
    if find(hash_hex):
        print(json.dumps({"recorded": False, "reason": "already-present", "hash": hash_hex}))
        return 0
    append({
        "hash": hash_hex,
        "name": args.name or "",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    print(json.dumps({"recorded": True, "hash": hash_hex, "ledger": str(LEDGER)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    for name in ("check", "record"):
        p = sub.add_parser(name)
        p.add_argument("--text-file", help="path to extracted UTF-8 text to hash (normalized)")
        p.add_argument("--file", help="path to a binary/image file to hash (raw bytes)")
        if name == "record":
            p.add_argument("--name", help="human label stored in the ledger")
    args = ap.parse_args()
    return cmd_check(args) if args.cmd == "check" else cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
