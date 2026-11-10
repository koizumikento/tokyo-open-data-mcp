import asyncio
import json
import sys
from argparse import SUPPRESS, ArgumentParser
from collections.abc import Sequence

import httpx

from .client import find_accessible_toilets


def run_cli(argv: Sequence[str]) -> None:
    parser = ArgumentParser(prog="tokyo-open-data-mcp")
    commands = parser.add_subparsers(required=True)

    command = commands.add_parser("find-accessible-toilets", argument_default=SUPPRESS)
    command.add_argument("--latitude", type=float, required=True)
    command.add_argument("--longitude", type=float, required=True)
    command.add_argument("--require-ostomate", action="store_true")
    command.add_argument("--require-ostomate-warm-water", action="store_true")
    command.add_argument("--require-universal-sheet", action="store_true")
    command.add_argument("--require-baby-changing-table", action="store_true")
    command.add_argument("--source-kind", choices=("facility", "rail"))
    command.add_argument("--limit", type=int)
    command.set_defaults(handler=find_accessible_toilets)

    arguments = vars(parser.parse_args(argv))
    handler = arguments.pop("handler")
    try:
        result = asyncio.run(handler(**arguments))
    except (ValueError, OSError, httpx.HTTPError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
