#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
from typing import Any
from wsgiref.simple_server import make_server

import falcon
import valkey
from dynaconf import Dynaconf

from cpe_guesser.bin.default import (
    DEFAULT_API_PORT,
    DEFAULT_CONFIG_SEARCH_LOCATIONS,
    DEFAULT_VALKEY_DB,
    DEFAULT_VALKEY_HOST,
    DEFAULT_VALKEY_PORT,
)
from cpe_guesser.db import Db


def api_error(msg: str) -> dict:
    return {"error": msg}


class SearchV1:
    def __init__(self, db: Db):
        self.db = db

    def on_post(self, req, resp):
        data_post = req.bounded_stream.read()
        js = data_post.decode("utf-8")

        try:
            q: dict[str, Any] = json.loads(js)
        except ValueError:
            resp.status = falcon.HTTP_400
            resp.media = api_error("expecting json data")
            return

        if not isinstance(q, dict):
            resp.status = falcon.HTTP_400
            resp.media = api_error("expecting data to be a json object")
            return

        keywords: list[str] = q["query"] if "query" in q else []
        limit: int | None = q["limit"] if "limit" in q else None

        if not isinstance(keywords, list):
            resp.status = falcon.HTTP_400
            resp.media = api_error("keywords must be a list")
            return

        if not all((isinstance(k, str) for k in keywords)):
            resp.status = falcon.HTTP_400
            resp.media = api_error("keywords must all be strings")
            return

        if limit is not None and not isinstance(limit, int):
            resp.status = falcon.HTTP_400
            resp.media = api_error("limit must be an integer")
            return

        r = self.db.v1_guess_cpe(keywords, limit=limit)

        resp.media = r


class SearchV2:
    def __init__(self, db: Db):
        self.db = db

    def on_post(self, req, resp):
        data_post = req.bounded_stream.read()
        js = data_post.decode("utf-8")

        try:
            q: dict[str, Any] = json.loads(js)
        except ValueError:
            resp.status = falcon.HTTP_400
            resp.media = api_error("expecting json data")
            return

        if not isinstance(q, dict):
            resp.status = falcon.HTTP_400
            resp.media = api_error("expecting data to be a json object")
            return

        keywords: list[str] = q["query"] if "query" in q else []
        vendor: str | None = q["vendor"] if "vendor" in q else None
        product: str | None = q["product"] if "product" in q else None
        limit: int = q["limit"] if "limit" in q else 10

        if not isinstance(keywords, list):
            resp.status = falcon.HTTP_400
            resp.media = api_error("keywords must be a list")
            return

        if not all((isinstance(k, str) for k in keywords)):
            resp.status = falcon.HTTP_400
            resp.media = api_error("keywords must all be strings")
            return

        if vendor is not None and not isinstance(vendor, str):
            resp.status = falcon.HTTP_400
            resp.media = api_error("vendor must be a string")
            return

        if product is not None and not isinstance(product, (str, None)):
            resp.status = falcon.HTTP_400
            resp.media = api_error("product must be a string")
            return

        if limit is not None and not isinstance(limit, int):
            resp.status = falcon.HTTP_400
            resp.media = api_error("limit must be an integer")
            return

        resp.media = self.db.search_abritrary_text(
            "\n".join(keywords),
            vendor=vendor,
            product=product,
            limit=limit,
        )


def main():
    parser = argparse.ArgumentParser(
        description="CPE guesser HTTP API server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help=f"Path to a custom configuration file. If this is unspecified configuration will be read from the first existing file of: {', '.join(DEFAULT_CONFIG_SEARCH_LOCATIONS)}",
    )

    args = parser.parse_args()

    # Configuration
    settings = Dynaconf(
        settings_files=DEFAULT_CONFIG_SEARCH_LOCATIONS
        if not args.config
        else [args.config]
    )

    # Database Configuration
    valkey_host = settings.get("valkey.host", DEFAULT_VALKEY_HOST)
    valkey_port = settings.get("valkey.port", DEFAULT_VALKEY_PORT)
    valkey_db = settings.get("valkey.db", DEFAULT_VALKEY_DB)

    # API Configuration
    api_port = settings.get("server.port", DEFAULT_API_PORT)

    vdb = valkey.Valkey(
        host=valkey_host, port=valkey_port, db=valkey_db, decode_responses=True
    )

    db = Db(vdb)

    app = falcon.App()
    app.add_route("/v1/search", SearchV1(db))
    app.add_route("/v2/search", SearchV2(db))

    try:
        with make_server("", api_port, app) as httpd:
            print(f"Serving on port {api_port}...")
            httpd.serve_forever()
    except OSError as e:
        print(e)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
