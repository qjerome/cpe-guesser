# -*- coding: utf-8 -*-
import argparse
import json

import valkey
from dynaconf import Dynaconf

from cpe_guesser.db import Db

# Configuration
settings = Dynaconf(settings_files=["../config/settings.yaml"])
valkey_host = settings.get("valkey.host", "127.0.0.1")
valkey_port = settings.get("valkey.port", 6379)
valkey_db = settings.get("valkey.db", 8)


def main():
    parser = argparse.ArgumentParser(
        description="Find potential CPE names from a list of keyword(s) and return a JSON of the results"
    )

    parser.add_argument("-v", "--vendor", type=str, help="Vendor to search for")
    parser.add_argument("-p", "--product", type=str, help="Product to search for")

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

    vdb = valkey.Valkey(
        host=valkey_host, port=valkey_port, db=valkey_db, decode_responses=True
    )

    db = Db(vdb)

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
