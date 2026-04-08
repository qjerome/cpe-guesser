"""
This module provides the base classes and functions for handling CPE (Common Platform Enumeration) data.

Classes:
    CPEFormatException: Exception raised when a CPE string is malformed.
    CPE: Represents a CPE entry with version, category, vendor, and product information.
"""

import re
import string
from typing import Iterator

from packaging import version
from packaging.version import InvalidVersion, Version

RE_VERSION = re.compile(r"(\d+\.\d+(\.\d+)?)")
TOKENIZE_RE = re.compile(rf"[\s{string.punctuation}\\]")


class CPEFormatException(Exception):
    """Exception raised when a CPE string is malformed or invalid."""

    pass


class CPE:
    @staticmethod
    def tokenize_cpe_str(s: str) -> Iterator[str]:
        return filter(lambda s: len(s) > 0, TOKENIZE_RE.split(s.lower()))

    @staticmethod
    def normalize_str(s: str) -> str:
        return CPE.normalize_tokenized_str(CPE.tokenize_cpe_str(s))

    @staticmethod
    def normalize_tokenized_str(s: Iterator[str]) -> str:
        return "-".join(s)

    """
    Represents a CPE (Common Platform Enumeration) entry.

    This class encapsulates the core components of a CPE entry, including version, category,
    vendor, and product. It provides methods for parsing raw CPE strings and converting
    CPE objects back to their string representation.

    Attributes:
        version (str): The CPE version (e.g., "2.3").
        category (str): The CPE category (e.g., "h" for hardware, "a" for application).
        vendor (str): The vendor name (e.g., "microsoft").
        product (str): The product name (e.g., "windows_10").
    """

    def __init__(
        self,
        version: str,
        category: str,
        vendor: str,
        product: str,
        product_version: str | None,
    ):
        """
        Initializes a new CPE instance.

        Args:
            version: The CPE version (e.g., "2.3").
            category: The CPE category (e.g., "h" for hardware, "a" for application).
            vendor: The vendor name (e.g., "microsoft").
            product: The product name (e.g., "windows_10").
        """
        self.version = version
        self.category = category
        self.vendor = vendor
        self.product = product
        self.product_version = product_version

    def to_cpe_str(self, strip_prod_version=False) -> str:
        """
        Converts the CPE object to its string representation.

        Returns:
            A string in the format "cpe:version:category:vendor:product".

        Example:
            >>> cpe = CPE("2.3", "h", "microsoft", "windows_10")
            >>> cpe.to_cpe_str()
            "cpe:2.3:h:microsoft:windows_10"
        """
        if strip_prod_version or self.product_version is None:
            return f"cpe:{self.version}:{self.category}:{self.vendor}:{self.product}"
        return f"cpe:{self.version}:{self.category}:{self.vendor}:{self.product}:{self.product_version}"

    def tokenize_vendor(self) -> Iterator[str]:
        """
        Splits the vendor name into tokens using underscores as delimiters.

        Returns:
            A list of vendor name tokens.

        Example:
            >>> cpe = CPE("2.3", "h", "microsoft_corp", "windows_10")
            >>> cpe.tokenize_vendor()
            ["microsoft", "corp"]
        """
        return CPE.tokenize_cpe_str(self.vendor)

    @property
    def normalized_vendor(self) -> str:
        return CPE.normalize_str(self.vendor)

    def tokenize_product(self) -> Iterator[str]:
        """
        Splits the product name into tokens using underscores as delimiters.

        Returns:
            A list of product name tokens.

        Example:
            >>> cpe = CPE("2.3", "h", "microsoft", "windows_10_pro")
            >>> cpe.tokenize_product()
            ["windows", "10", "pro"]
        """
        return CPE.tokenize_cpe_str(self.product)

    @property
    def normalized_product(self) -> str:
        return CPE.normalize_str(self.product)

    def tokenize_version(self) -> set[str]:
        if self.product_version is None:
            return set()

        tokens = set()
        v = self.parse_product_version()
        if v is not None:
            tokens.add(f"{v.major}.{v.minor}.{v.micro}")
            tokens.add(f"{v.major}.{v.minor}")
            tokens.add(f"{v.major}")

        tokens.add(self.product_version)
        tokens.update(self.product_version.split("."))
        tokens.update(self.product_version.split("-"))
        # some products have weird product version so we somehow bruteforce the game
        for m in RE_VERSION.findall(self.product_version):
            if len(m) > 0:
                tokens.add(m[0])

        return tokens

    def tokenize_category(self) -> list[str]:
        if self.category == "a":
            return ["app", "application"]
        elif self.category == "o":
            return ["os", "operating", "system", "operating-system", "firmware"]
        elif self.category == "h":
            return ["hardware"]
        else:
            return []

    @staticmethod
    def parse(raw_cpe_line: str) -> "CPE":
        """
        Parses a raw CPE string and creates a new CPE object.

        This function splits a raw CPE line (e.g., `cpe:2.3:h:3com:3cb9e16:-:*:*:*:*:*:*:*`)
        and creates a new CPE object.

        Args:
            raw_cpe_line: A string representing a CPE entry.

        Returns:
            A new CPE object populated with the parsed data.

        Raises:
            CPEFormatException: If the CPE string is malformed or invalid.

        Example:
            >>> cpe = CPE.parse("cpe:2.3:h:microsoft:windows_10")
            >>> cpe.version
            "2.3"
        """
        sp = raw_cpe_line.split(":")

        if sp[0] != "cpe":
            raise CPEFormatException(
                "Invalid CPE format: expected 'cpe' as the first component"
            )

        if len(sp) < 5:
            raise CPEFormatException(
                "Invalid CPE format: at least 5 components are required"
            )

        product_version = sp[5] if len(sp) >= 6 else None

        return CPE(sp[1], sp[2], sp[3], sp[4], product_version)

    def parse_product_version(self) -> None | Version:
        """
        Parses the version string of the CPE object.

        This method attempts to parse the version string using the `packaging.version.parse` function.
        If the version string is invalid, it returns `None`.

        Returns:
            A `Version` object if the version string is valid, otherwise `None`.

        Example:
            >>> cpe = CPE("2.3", "h", "microsoft", "windows_10", "1.2.3")
            >>> cpe.parse_version()
            <Version('1.2.3')>
            >>> cpe = CPE("2.3", "h", "microsoft", "windows_10", "invalid")
            >>> cpe.parse_version() is None
            True
        """
        try:
            if self.product_version is None:
                return None
            return version.parse(self.product_version)
        except InvalidVersion:
            return None

    def __hash__(self) -> int:
        """
        Makes CPE objects hashable so they can be stored in sets and used as dict keys.

        Returns:
            A hash value based on the CPE's core attributes.
        """
        # Use a tuple of the core attributes for hashing
        return hash(
            (
                self.version,
                self.category,
                self.vendor,
                self.product,
                self.product_version,
            )
        )

    def __eq__(self, other: object) -> bool:
        """
        Defines equality comparison for CPE objects.

        Args:
            other: Another object to compare with.

        Returns:
            True if the objects are equal CPEs, False otherwise.
        """
        if not isinstance(other, CPE):
            return False
        return (
            self.version == other.version
            and self.category == other.category
            and self.vendor == other.vendor
            and self.product == other.product
            and self.product_version == other.product_version
        )

    def __str__(self) -> str:
        return self.to_cpe_str()
