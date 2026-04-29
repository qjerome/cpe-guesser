# -*- coding: utf-8 -*-
import argparse
import gzip
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from typing import Iterator
from urllib.parse import urlparse

import valkey
from dynaconf import Dynaconf
from valkey.client import Valkey

from cpe_guesser.bin.default import (
    DEFAULT_CONFIG_SEARCH_LOCATIONS,
    DEFAULT_DOWNLOAD_PATH,
    DEFAULT_VALKEY_DB,
    DEFAULT_VALKEY_HOST,
    DEFAULT_VALKEY_PORT,
)
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

FILE_KIND_PLAIN = "plain-text"
FILE_KIND_TAR_GZ = "tar-gz"
FILE_KIND_GZ = "gz"
FILE_KIND_UNKNOWN = "unknown"

CPE_IMPORT_CACHED_ENV_VAR = "CPE_IMPORT_CACHED"


def dbsize(rdb: Valkey) -> int:
    dbsize = rdb.dbsize()
    if isinstance(dbsize, int):
        return dbsize
    return 0


def wait_db(rdb: Valkey, timeout_sec: int = 30) -> bool:
    timeout = time.time() + timeout_sec
    while time.time() < timeout:
        try:
            if rdb.ping():
                return True
        except Exception as e:
            print(f"Waiting database to be ready: {e}")
        time.sleep(1)
    return False


def str_to_bool(s: str) -> bool:
    return s.lower() in ["y", "yes", "true", "t", "1"]


def file_path_kind(path: str) -> str:
    if path.endswith(".tar.gz"):
        kind = FILE_KIND_TAR_GZ
    elif path.endswith(".gz"):
        kind = FILE_KIND_GZ
    elif any((path.endswith(ext) for ext in [".json", ".ndjson", ".txt"])):
        kind = FILE_KIND_PLAIN
    else:
        kind = FILE_KIND_UNKNOWN
    return kind


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
            print(f"Processed {i} cpes")
            db.commit()
    # we need to commit the last batch
    db.commit()
    print(f"Total CPEs inserted: {i}")


def main():
    parser = argparse.ArgumentParser(
        description="Initializes the Redis database with CPE dictionary.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help=f"Path to a custom configuration file. If this is unspecified configuration will be read from the first existing file of: {', '.join(DEFAULT_CONFIG_SEARCH_LOCATIONS)}",
    )

    parser.add_argument(
        "--cached",
        action="store_true",
        help=f"When processing URL, use cached files in download directory if possible else attempt to download file. If this flag is not specified an attempt to read value from environment variable {CPE_IMPORT_CACHED_ENV_VAR} will be made.",
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
        help="Flush and repopulate the CPE database.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds to wait for the database to be ready",
    )

    parser.add_argument(
        "CPE_FILE_OR_URL", type=str, help="File containing CPE data in specified format"
    )

    args = parser.parse_args()

    # Configuration
    settings = Dynaconf(
        settings_files=DEFAULT_CONFIG_SEARCH_LOCATIONS
        if not args.config
        else [args.config]
    )
    downloads_path = settings.get("downloads.path", DEFAULT_DOWNLOAD_PATH)
    valkey_host = settings.get("valkey.host", DEFAULT_VALKEY_HOST)
    valkey_port = settings.get("valkey.port", DEFAULT_VALKEY_PORT)
    valkey_db = settings.get("valkey.db", DEFAULT_VALKEY_DB)

    if not args.format:
        parser.error("--format|-f must be specified")

    if not args.cached and "CPE_IMPORT_CACHED" in os.environ:
        args.cached = str_to_bool(os.environ["CPE_IMPORT_CACHED"])

    rdb = valkey.Valkey(host=valkey_host, port=valkey_port, db=valkey_db)
    if not wait_db(rdb, args.timeout):
        print("Database is not available, try later or increase timeout")
        sys.exit(1)

    cpe_file_or_url = args.CPE_FILE_OR_URL

    if rdb.dbsize() > 0 and args.replace:  # ty:ignore[unsupported-operator]
        print(f"Flushing {rdb.dbsize()} keys from the database...")
        rdb.flushdb()

    if cpe_file_or_url.startswith("http://") or cpe_file_or_url.startswith("https://"):
        dest_path: str = os.path.join(
            downloads_path, os.path.basename(urlparse(cpe_file_or_url).path)
        )

        kind = file_path_kind(dest_path)
        if kind == FILE_KIND_PLAIN:
            dest_path = f"{dest_path}.gz"

        if not args.cached or not os.path.isfile(dest_path):
            print(f"Downloading: {cpe_file_or_url} to {dest_path}")
            with urllib.request.urlopen(cpe_file_or_url) as response:
                if kind == FILE_KIND_PLAIN:
                    # we save a compressed version of the file
                    with open(dest_path, "wb") as f:
                        with gzip.GzipFile(fileobj=f, mode="w") as gz:
                            shutil.copyfileobj(response, gz)
                else:
                    # we save file as is
                    with open(dest_path, "wb") as f:
                        shutil.copyfileobj(response, f)

        cpe_file_or_url: str = dest_path

    if cpe_file_or_url == "-":
        print("Using stdin ...")
    else:
        print(f"Using existing file {cpe_file_or_url} ...")

    print("Populating the database (please be patient)...")

    cpe_file_kind = file_path_kind(cpe_file_or_url)
    if args.format == FORMAT_NVD_JSON:
        with Db(rdb) as db:
            processed: set[str] = set()
            reader: CPEReader = NVDCPEReader(cpe_file_or_url)
            n_cpes = 0
            for cpe in reader.read_cpes():
                if reader.processing_file not in processed:
                    db.commit()
                    if n_cpes != 0:
                        print(f"NVD importer: processed {n_cpes} CPEs")
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
                reader = GenericCPEReader("stdin", stream=sys.stdin)
            else:
                if cpe_file_kind == FILE_KIND_GZ:
                    with gzip.GzipFile(cpe_file_or_url, mode="r") as gz:
                        reader = GenericCPEReader(cpe_file_or_url, stream=gz)
                        generic_insert_cpe(db, reader.read_cpes())
                else:
                    reader = GenericCPEReader(cpe_file_or_url)
                    generic_insert_cpe(db, reader.read_cpes())

    else:
        print(f"Error! No handler for the file type of {cpe_file_or_url}")
        sys.exit(1)

    print(f"Done! {rdb.dbsize()} keys inserted.")


if __name__ == "__main__":
    main()
