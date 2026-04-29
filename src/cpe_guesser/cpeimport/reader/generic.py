import codecs
import re
import string
from gzip import GzipFile
from pathlib import Path
from typing import Generator, Iterator, TextIO

from cpe_guesser.cpe import CPE
from cpe_guesser.cpeimport.reader import CPEReader

# we need to be carefull not to count escaped : as normal split point
CPE_2_3_PATTERN = rf"cpe:2\.3(:((\\:)|.)*?){{11}}[{string.punctuation}]"
CPE_REGEX = re.compile(CPE_2_3_PATTERN)


def line_generator(tio: TextIO | GzipFile) -> Generator[str, None, None]:
    line = tio.readline()
    while len(line) > 0:
        # if we read from a gzip file
        if isinstance(line, bytes):
            line = line.decode("utf8")
        yield line.rstrip()
        line = tio.readline()


def sanitize_escapes(s: str) -> str:
    if r"\\" in s:
        tmp = codecs.decode(s, "unicode-escape")
        while s != tmp:
            s = tmp
            tmp = codecs.decode(s, "unicode-escape")
    return s


class GenericCPEReader(CPEReader):
    """
    Concrete implementation of CPEReader for reading CPEs from any text file.

    This reader extracts CPE 2.3 strings using regex pattern matching and
    provides methods to iterate over found CPE strings or parsed CPE objects.
    """

    def __init__(self, filepath: str | Path, stream: None | TextIO | GzipFile = None):
        """
        Initialize the GenericCPEReader.

        Args:
            filepath: Path to the text file to read, or a path string.
            text_io: Optional text IO stream. If provided, filepath is used
                only for reference and the stream is read directly.
        """
        self.filepath = filepath
        self._tio = stream
        self.skipped = 0
        self.n_cpe_read = 0

    def find_all_cpe_str(self) -> Iterator[str]:
        """
        Find all unique CPE 2.3 strings in the input.

        Uses regex pattern matching to extract CPE strings from each line and
        handles CPE deduplication.

        Returns:
            An iterator of unique CPE 2.3 strings found in the input.

        Note:
            Handles double-escaped CPE strings (e.g., from JSON) by converting
            them back to normal escape sequences.
        """
        cache = set()

        if self._tio is None:
            with open(self.filepath) as fd:
                for line in line_generator(fd):
                    for cpe_str in map(
                        # it may happen that we want to brutally get string from json
                        # so we need to get rid of double escaping and convert back to
                        # normal escape
                        lambda m: sanitize_escapes(m.group(0)),
                        CPE_REGEX.finditer(line),
                    ):
                        h = CPE.uuid5(cpe_str)
                        if h in cache:
                            continue
                        self.n_cpe_read += 1
                        yield cpe_str
                        cache.add(h)
        else:
            for line in line_generator(self._tio):
                for cpe_str in map(
                    # it may happen that we want to brutally get string from json
                    # so we need to get rid of double escaping and convert back to
                    # normal escape
                    lambda m: sanitize_escapes(m.group(0)),
                    CPE_REGEX.finditer(line),
                ):
                    h = CPE.uuid5(cpe_str)
                    if h in cache:
                        continue
                    self.n_cpe_read += 1
                    yield cpe_str
                    cache.add(h)

    def read_cpes(self) -> Iterator[CPE]:
        """
        Read CPEs from a text file.

        Parses each CPE string found by find_all_cpe_str() into a CPE object.

        Returns:
            An iterator of CPE objects parsed from the text file.
        """

        for cpe_str in self.find_all_cpe_str():
            yield CPE.parse_strict(cpe_str)
