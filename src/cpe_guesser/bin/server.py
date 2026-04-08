#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from typing import Any
from wsgiref.simple_server import make_server

import falcon
import valkey
from dynaconf import Dynaconf

from cpe_guesser.db import Db

# API Configuration
settings = Dynaconf(settings_files=["../config/settings.yaml"])
port = settings.get("server.port", 8000)

# Database Configuration
settings = Dynaconf(settings_files=["../config/settings.yaml"])
valkey_host = settings.get("valkey.host", "127.0.0.1")
valkey_port = settings.get("valkey.port", 6666)
valkey_db = settings.get("valkey.db", 8)

vdb = valkey.Valkey(
    host=valkey_host, port=valkey_port, db=valkey_db, decode_responses=True
)

db = Db(vdb)


def api_error(msg: str) -> dict:
    return {"error": msg}


class SearchV1:
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

        r = db.v1_guess_cpe(keywords, limit=limit)

        resp.media = r


class SearchV2:
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

        resp.media = db.search_abritrary_text(
            "\n".join(keywords),
            vendor=vendor,
            product=product,
            limit=limit,
        )


def main():
    app = falcon.App()
    app.add_route("/v1/search", SearchV1())
    app.add_route("/v2/search", SearchV2())

    try:
        with make_server("", port, app) as httpd:
            print(f"Serving on port {port}...")
            httpd.serve_forever()
    except OSError as e:
        print(e)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
