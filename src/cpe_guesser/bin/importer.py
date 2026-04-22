# -*- coding: utf-8 -*-
import argparse
import gzip
import os
import shutil
import sys
import urllib.error
import urllib.request
from typing import Iterator
from urllib.parse import urlparse

import valkey
from dynaconf import Dynaconf
from valkey.client import Valkey

from cpe_guesser.cpe import CPE
from cpe_guesser.cpeimport.reader import CPEReader
from cpe_guesser.cpeimport.reader.generic import GenericCPEReader, line_generator
from cpe_guesser.cpeimport.reader.nvd_json import NVDCPEReader
from cpe_guesser.db import Db

DEFAULT_CPE_BATCH_SIZE = 20_000

# NVD JSON format
FORMAT_NVD_JSON = "nvd-json"
# New line delimited CPE string
FORMAT_ND_CPE = "nd-cpe"
# Any text
FORMAT_ANY_TEXT = "any-text"

# Configuration
settings = Dynaconf(settings_files=["../config/settings.yaml"])
download_path = settings.get("download.path", "./data")
valkey_host = settings.get("valkey.host", "127.0.0.1")
valkey_port = settings.get("valkey.port", 6666)
valkey_db = settings.get("valkey.db", 8)


def dbsize(rdb: Valkey) -> int:
    dbsize = rdb.dbsize()
    if isinstance(dbsize, int):
        return dbsize
    return 0


def generic_insert_cpe_str(
    db: Db, cpe_lines: Iterator[str], batch_size=DEFAULT_CPE_BATCH_SIZE
):
    generic_insert_cpe(
        db, map(lambda x: CPE.parse_strict(x), cpe_lines), batch_size=batch_size
    )


def generic_insert_cpe(
    db: Db, cpe_it: Iterator[CPE], batch_size=DEFAULT_CPE_BATCH_SIZE
):
    for i, cpe in enumerate(cpe_it):
        db.insert_pipeline(cpe)
        if i % batch_size == 0:
            print(f"Inserted {i} cpes")
            db.commit()
    # we need to commit the last batch
    db.commit()
    print(f"Total CPEs inserted: {i}")


def main():
    parser = argparse.ArgumentParser(
        description="Initializes the Redis database with CPE dictionary."
    )
    parser.add_argument(
        "--download",
        "-d",
        action="store_true",
        default=False,
        help="Download the CPE dictionary even if it already exists.",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=[FORMAT_NVD_JSON, FORMAT_ND_CPE, FORMAT_ANY_TEXT],
        help="Input format for data",
    )

    parser.add_argument("--force", action="store_true", help="Force data insertion")

    parser.add_argument(
        "--replace",
        "-r",
        action="store_true",
        default=False,
        help="Flush and repopulated the CPE database.",
    )

    parser.add_argument(
        "CPE_FILE_OR_URL", type=str, help="File containing CPE data in specified format"
    )

    args = parser.parse_args()

    if not args.format:
        parser.error("--format|-f must be specified")

    rdb = valkey.Valkey(host=valkey_host, port=valkey_port, db=valkey_db)

    cpe_file_or_url = args.CPE_FILE_OR_URL

    if not args.replace and dbsize(rdb) > 0 and not args.force:
        print(f"Warning! The Redis database already has {rdb.dbsize()} keys.")
        print("Use --replace if you want to flush the database and repopulate it.")
        sys.exit(0)

    if rdb.dbsize() > 0 and args.replace:  # ty:ignore[unsupported-operator]
        print(f"Flushing {rdb.dbsize()} keys from the database...")
        rdb.flushdb()

    if cpe_file_or_url.startswith("http://") or cpe_file_or_url.startswith("https://"):
        dest_path: str = os.path.join(
            download_path, os.path.basename(urlparse(cpe_file_or_url).path)
        )
        uncompress_path = dest_path.rstrip(".gz")
        if args.download:
            print(f"Downloading: {cpe_file_or_url}")
            urllib.request.urlretrieve(cpe_file_or_url, dest_path)
        cpe_file_or_url: str = dest_path
        if dest_path.endswith(".gz") and os.path.isfile(dest_path):
            print(f"Uncompressing {dest_path} ...")
            with gzip.open(dest_path, "rb") as f_in:
                with open(uncompress_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(dest_path)
        cpe_file_or_url = uncompress_path

    if cpe_file_or_url == "-":
        print("Using stdin ...")
    else:
        print(f"Using existing file {cpe_file_or_url} ...")

    print("Populating the database (please be patient)...")

    if args.format == FORMAT_NVD_JSON:
        with Db(rdb) as db:
            processed: set[str] = set()
            reader: CPEReader = NVDCPEReader(cpe_file_or_url)
            n_cpes = 0
            for cpe in reader.read_cpes():
                if reader.processing_file not in processed:
                    db.commit()
                    if n_cpes != 0:
                        print(f"{n_cpes} CPEs in database")
                    print(f"processing: {reader.processing_file}")
                    if reader.processing_file is not None:
                        processed.add(reader.processing_file)
                db.insert_pipeline(cpe)
                n_cpes += 1
            db.commit()
    elif args.format == FORMAT_ND_CPE:
        with Db(rdb) as db:
            if cpe_file_or_url == "-":
                generic_insert_cpe_str(db, line_generator(sys.stdin))
            else:
                with open(cpe_file_or_url) as fd:
                    generic_insert_cpe_str(db, line_generator(fd))
    elif args.format == FORMAT_ANY_TEXT:
        with Db(rdb) as db:
            if cpe_file_or_url == "-":
                reader = GenericCPEReader("stdin", text_io=sys.stdin)
            else:
                reader = GenericCPEReader(cpe_file_or_url)

            generic_insert_cpe(db, reader.read_cpes())

    else:
        print(f"Error! No handler for the file type of {cpe_file_or_url}")
        sys.exit(1)

    print(f"Done! {rdb.dbsize()} keys inserted.")


if __name__ == "__main__":
    main()
