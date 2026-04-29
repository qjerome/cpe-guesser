# -*- coding: utf-8 -*-
import argparse
import json

import valkey
from dynaconf import Dynaconf

from cpe_guesser.bin.default import (
    DEFAULT_CONFIG_SEARCH_LOCATIONS,
    DEFAULT_VALKEY_DB,
    DEFAULT_VALKEY_HOST,
    DEFAULT_VALKEY_PORT,
)
from cpe_guesser.db import Db


def main():
    parser = argparse.ArgumentParser(
        description="Find potential CPE names from a list of keyword(s) and return a JSON of the results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help=f"Path to a custom configuration file. If this is unspecified configuration will be read from the first existing file of: {', '.join(DEFAULT_CONFIG_SEARCH_LOCATIONS)}",
    )

    parser.add_argument("-v", "--vendor", type=str, help="Vendor to search for")
    parser.add_argument("-p", "--product", type=str, help="Product to search for")
    parser.add_argument(
        "-V",
        "--version",
        type=int,
        choices=[1, 2],
        default=2,
        help="Version of the guessing function.",
    )

    parser.add_argument(
        "word",
        metavar="WORD",
        type=str,
        nargs="*",
        help="One or more keyword(s) to lookup",
    )

    parser.add_argument(
        "--unique",
        action="store_true",
        help="Return the best CPE matching the keywords given",
        default=False,
    )

    parser.add_argument(
        "-l", "--limit", type=int, default=10, help="Limit the number of results"
    )

    parser.add_argument("-a", "--all", action="store_true", help="Show all results")

    args = parser.parse_args()

    # Configuration
    settings = Dynaconf(
        settings_files=DEFAULT_CONFIG_SEARCH_LOCATIONS
        if not args.config
        else [args.config]
    )
    valkey_host = settings.get("valkey.host", DEFAULT_VALKEY_HOST)
    valkey_port = settings.get("valkey.port", DEFAULT_VALKEY_PORT)
    valkey_db = settings.get("valkey.db", DEFAULT_VALKEY_DB)

    vdb = valkey.Valkey(
        host=valkey_host, port=valkey_port, db=valkey_db, decode_responses=True
    )

    db = Db(vdb)

    if args.unique:
        args.limit = 1

    if args.version == 1:
        print(
            json.dumps(
                db.v1_guess_cpe(
                    args.word,
                    limit=None if args.all else args.limit,
                )
            )
        )

    else:
        print(
            json.dumps(
                db.search_abritrary_text(
                    "\n".join(args.word),
                    vendor=args.vendor,
                    product=args.product,
                    limit=None if args.all else args.limit,
                )
            )
        )


if __name__ == "__main__":
    main()
