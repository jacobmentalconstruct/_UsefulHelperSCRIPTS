"""
CLI interface for the _theCELL Scratchpad system.

Usage:
    python -m src.scratchpad list
    python -m src.scratchpad read <name> [--section <s>] [--json]
    python -m src.scratchpad write <name> <content> [--section <s>] [--author <a>]
    python -m src.scratchpad edit <entry_id> <content>
    python -m src.scratchpad delete <entry_id>
    python -m src.scratchpad sections <name>
    python -m src.scratchpad clear <name> [--section <s>]
    python -m src.scratchpad ai <name> <instruction> [--model <m>] [--section <s>]
    python -m src.scratchpad drop <name>

Any agent or script can also import directly:
    from src.microservices._ScratchpadMS import ScratchpadMS
    pad = ScratchpadMS(db_path="path/to/db")
    pad.write("notes", "hello", author="user")
"""
import argparse
import json
import os
import sys


def _get_db_path():
    """Resolves the default scratchpad DB path relative to project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_dir = os.path.join(project_root, "_db")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "scratchpad.db")


def _get_pad(db_path=None):
    from src.microservices._ScratchpadMS import ScratchpadMS
    return ScratchpadMS(db_path=db_path or _get_db_path())


def _get_engine():
    from src.microservices._IngestEngineMS import IngestEngineMS
    return IngestEngineMS()


def cmd_list(args):
    pad = _get_pad(args.db)
    pads = pad.list_pads()
    if not pads:
        print("No scratchpads found.")
        return
    for p in pads:
        sections = ", ".join(p.sections) if p.sections else "empty"
        print(f"  {p.name}  ({p.entry_count} entries)  sections: [{sections}]  updated: {p.updated_at}")


def cmd_read(args):
    pad = _get_pad(args.db)
    entries = pad.read(args.name, section=args.section)
    if not entries:
        print(f"No entries in '{args.name}'" + (f"/{args.section}" if args.section else "") + ".")
        return
    if args.json:
        print(json.dumps([e.dict() for e in entries], indent=2))
    else:
        for e in entries:
            header = f"[{e.id}] [{e.author.upper()}]"
            if e.section != "default":
                header += f" ({e.section})"
            print(f"{header}  {e.created_at}")
            print(f"  {e.content}")
            print()


def cmd_write(args):
    pad = _get_pad(args.db)
    # Support reading from stdin with "-"
    content = args.content
    if content == "-":
        content = sys.stdin.read()
    entry = pad.write(args.name, content, author=args.author, section=args.section)
    print(f"Written entry #{entry.id} to '{args.name}/{entry.section}' as {entry.author}")


def cmd_edit(args):
    pad = _get_pad(args.db)
    result = pad.update_entry(args.entry_id, args.content)
    if result:
        print(f"Updated entry #{result.id}")
    else:
        print(f"Entry #{args.entry_id} not found.", file=sys.stderr)
        sys.exit(1)


def cmd_delete(args):
    pad = _get_pad(args.db)
    if pad.delete_entry(args.entry_id):
        print(f"Deleted entry #{args.entry_id}")
    else:
        print(f"Entry #{args.entry_id} not found.", file=sys.stderr)
        sys.exit(1)


def cmd_sections(args):
    pad = _get_pad(args.db)
    sections = pad.get_sections(args.name)
    if not sections:
        print(f"No sections in '{args.name}'.")
        return
    for s in sections:
        print(f"  {s}")


def cmd_clear(args):
    pad = _get_pad(args.db)
    if pad.clear(args.name, section=args.section):
        target = f"'{args.name}'"
        if args.section:
            target += f"/{args.section}"
        print(f"Cleared {target}")
    else:
        print(f"Scratchpad '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)


def cmd_drop(args):
    pad = _get_pad(args.db)
    if pad.delete_pad(args.name):
        print(f"Deleted scratchpad '{args.name}'")
    else:
        print(f"Scratchpad '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)


def cmd_ai(args):
    pad = _get_pad(args.db)
    engine = _get_engine()
    pad.engine = engine

    if not engine.check_ollama_connection():
        print("Error: Cannot connect to Ollama at localhost:11434", file=sys.stderr)
        sys.exit(1)

    print(f"Processing '{args.name}' with instruction: {args.instruction[:80]}...")
    entry = pad.ai_process(args.name, args.instruction, model=args.model, section=args.section)
    print(f"\n[AI] entry #{entry.id} written to '{args.name}/{entry.section}':")
    print(entry.content)


def main():
    parser = argparse.ArgumentParser(
        prog="scratchpad",
        description="_theCELL Scratchpad — collaborative notepad for user and AI"
    )
    parser.add_argument("--db", default=None, help="Path to scratchpad SQLite DB (default: _db/scratchpad.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List all scratchpads")

    # read
    p_read = sub.add_parser("read", help="Read entries from a scratchpad")
    p_read.add_argument("name", help="Scratchpad name")
    p_read.add_argument("--section", "-s", default=None, help="Filter by section")
    p_read.add_argument("--json", action="store_true", help="Output as JSON")

    # write
    p_write = sub.add_parser("write", help="Write an entry to a scratchpad")
    p_write.add_argument("name", help="Scratchpad name (auto-created if new)")
    p_write.add_argument("content", help="Content to write (use '-' for stdin)")
    p_write.add_argument("--section", "-s", default="default", help="Section name")
    p_write.add_argument("--author", "-a", default="user", help="Author tag (user/ai)")

    # edit
    p_edit = sub.add_parser("edit", help="Edit an existing entry")
    p_edit.add_argument("entry_id", type=int, help="Entry ID to edit")
    p_edit.add_argument("content", help="New content")

    # delete
    p_del = sub.add_parser("delete", help="Delete a single entry")
    p_del.add_argument("entry_id", type=int, help="Entry ID to delete")

    # sections
    p_sec = sub.add_parser("sections", help="List sections in a scratchpad")
    p_sec.add_argument("name", help="Scratchpad name")

    # clear
    p_clear = sub.add_parser("clear", help="Clear all entries from a scratchpad")
    p_clear.add_argument("name", help="Scratchpad name")
    p_clear.add_argument("--section", "-s", default=None, help="Only clear this section")

    # drop
    p_drop = sub.add_parser("drop", help="Delete an entire scratchpad")
    p_drop.add_argument("name", help="Scratchpad name to delete")

    # ai
    p_ai = sub.add_parser("ai", help="AI processes the scratchpad content")
    p_ai.add_argument("name", help="Scratchpad name")
    p_ai.add_argument("instruction", help="Instruction for the AI")
    p_ai.add_argument("--model", "-m", default=None, help="Ollama model name")
    p_ai.add_argument("--section", "-s", default=None, help="Section to process")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "read": cmd_read,
        "write": cmd_write,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "sections": cmd_sections,
        "clear": cmd_clear,
        "drop": cmd_drop,
        "ai": cmd_ai,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
