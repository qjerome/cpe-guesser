from abc import ABC, abstractmethod
from typing import Iterator

from cpe_guesser.cpe import CPE


class CPEReader(ABC):
    """
    Abstract base class for CPE readers.

    Subclasses must implement the read_cpes() method to provide
    specific CPE reading functionality.
    """

    @abstractmethod
    def read_cpes(self) -> Iterator[CPE]:
        """
        Read CPEs from a source and return them as an iterator.

        This method must be implemented by subclasses to provide
        specific CPE reading functionality.

        Returns:
            An iterator of CPE objects.
        """
        pass
