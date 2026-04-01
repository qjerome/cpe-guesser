import json
import tarfile
from pathlib import Path
from typing import Iterator

from cpe_guesser.cpe import CPE
from cpe_guesser.cpeimport.reader import CPEReader


class NVDCPEReader(CPEReader):
    """
    Concrete implementation of CPEReader for reading CPEs from NVD JSON files.
    """

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.skipped = 0
        self.n_cpe_read = 0
        self.processing_file: str | None = None

    def read_cpes(self) -> Iterator[CPE]:
        """
        Read CPEs from an NVD JSON file.

        Returns:
            An iterator of CPE objects parsed from the JSON file.
        """
        """Parse both JSON files and tar archives containing JSON files."""
        if tarfile.is_tarfile(self.filepath):
            return self.read_tar_archive(self.filepath)
        elif str(self.filepath).endswith(".json"):
            with open(self.filepath, "r", encoding="utf-8") as f:
                return self.read_json_file(f)
        raise ValueError(f"Unsupported file type: {self.filepath}")

    def read_tar_archive(self, path) -> Iterator[CPE]:
        """Process each JSON file in a tar archive."""
        with tarfile.open(path, "r:*") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(".json"):
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        with extracted as f:
                            self.processing_file = member.name
                            for cpe in self.read_json_file(f):
                                yield cpe

    def read_json_file(self, fileobj) -> Iterator[CPE]:
        """Process a single JSON file."""
        try:
            data = json.load(fileobj)
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON file: {e}")
            return

        products = data.get("products")
        if not isinstance(products, list):
            print("Warning: 'products' key missing or not a list")
            return

        for product in products:
            try:
                p = self.process_product(product)
                if p is not None:
                    yield p
            except Exception as e:
                print(f"Skipping invalid product entry: {e}")

    def process_product(self, product: dict) -> CPE | None:
        """Process a single CPE product entry."""
        cpe_obj = product.get("cpe", {})
        if not cpe_obj or cpe_obj.get("deprecated", False):
            self.skipped += 1
            return
        cpe_line = cpe_obj.get("cpeName")
        if not cpe_line:
            return
        self.n_cpe_read += 1
        return CPE.parse(cpe_line)
