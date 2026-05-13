from __future__ import annotations

import argparse

from app.config import load_settings
from app.memory import AgentMemoryService
from app.storage import PostgresTaskStorage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage MyAgent long-term memory indexes.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    reset = subparsers.add_parser(
        "reset-qdrant",
        help="Delete and recreate the configured Qdrant memory collection.",
    )
    reset.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the destructive reset without an interactive prompt.",
    )
    rebuild = subparsers.add_parser(
        "rebuild-qdrant",
        help="Delete, recreate, and repopulate the Qdrant memory collection from Postgres.",
    )
    rebuild.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the destructive rebuild without an interactive prompt.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.command == "reset-qdrant":
        if not confirm_destructive_action(args.yes, "reset", settings.qdrant_collection):
            return 1
        service = AgentMemoryService(settings, storage=None)
        service.reset_index()
        print(
            "Reset Qdrant memory collection "
            f"'{settings.qdrant_collection}' with schema v2 payload contract."
        )
        return 0
    if args.command == "rebuild-qdrant":
        if not settings.database_url:
            parser.error("MYAGENT_DATABASE_URL is required for rebuild-qdrant")
        if not confirm_destructive_action(args.yes, "rebuild", settings.qdrant_collection):
            return 1
        storage = PostgresTaskStorage(settings.task_root, settings.database_url)
        storage.initialize()
        service = AgentMemoryService(settings, storage=storage)
        count = service.rebuild_index_from_storage()
        print(
            "Rebuilt Qdrant memory collection "
            f"'{settings.qdrant_collection}' with {count} canonical memory item(s)."
        )
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2


def confirm_destructive_action(yes: bool, action: str, collection: str) -> bool:
    if yes:
        return True
    answer = input(f"{action.title()} Qdrant collection '{collection}'? Type RESET to continue: ")
    if answer == "RESET":
        return True
    print("Aborted.")
    return False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
