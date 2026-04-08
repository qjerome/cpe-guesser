from typing import Iterable, Iterator

from valkey import Valkey
from valkey.client import Pipeline

from cpe_guesser.cpe import CPE, TOKENIZE_RE


def tokenize_text(text: str) -> list[str]:
    """
    Tokenizes text into words by splitting on whitespace and punctuation.

    This function splits the input text into tokens using whitespace and punctuation
    as delimiters, and filters out empty strings.

    Args:
        text: The input text to tokenize.

    Returns:
        A list of tokens (words) from the input text.

    Example:
        >>> tokenize_text("Hello, World! This is a test.")
        ['Hello', 'World', 'This', 'is', 'a', 'test']

        >>> tokenize_text("Python-3.9 and Rust")
        ['Python', '3', '9', 'and', 'Rust']
    """
    return list(
        filter(
            lambda x: len(x) > 0,
            TOKENIZE_RE.split(text),
        )
    )


def tokenize_text_lower(text: str) -> list[str]:
    """
    Tokenizes text into lowercase words, splitting on whitespace and punctuation.

    This function splits the input text into tokens using whitespace and punctuation
    as delimiters, converts all tokens to lowercase, and filters out empty strings.

    Args:
        text: The input text to tokenize.

    Returns:
        A list of lowercase tokens (words) from the input text.

    Example:
        >>> tokenize_text_lower("Hello, World! This is a test.")
        ['hello', 'world', 'this', 'is', 'a', 'test']

        >>> tokenize_text_lower("Python-3.9 and Rust")
        ['python', '3', '9', 'and', 'rust']
    """
    return tokenize_text(text.lower())


def find_upper_keywords_chains(tokens: list[str]) -> list[list[str]]:
    cap_kw: list[str] = []
    cap_kw_chains: list[list[str]] = []

    for i, t in enumerate(tokens):
        if len(t) > 0:
            if t[0].isupper():
                cap_kw.append(t)
                continue
            else:
                # don't need to take one word chain
                if len(cap_kw) > 1:
                    cap_kw_chains.append(cap_kw)
                    cap_kw = []

    return cap_kw_chains


def is_tokenized_full_match(
    keyword_index: dict[str, set[int]], tokens: list[str]
) -> bool:
    prev_tok = None

    if len(tokens) == 1:
        return tokens[0] in keyword_index

    for i, t in enumerate(tokens):
        if t not in keyword_index:
            break
        if prev_tok is None:
            prev_tok = t
            continue
        else:
            test = any((pos - 1 in keyword_index[prev_tok] for pos in keyword_index[t]))
            if not test:
                break
            prev_tok = t
            # we are at the last element so we have full match
            if i == len(tokens) - 1:
                return True
    return False


def map_str_to_cpe(i: Iterable[str]) -> Iterator[CPE]:
    return map(lambda s: CPE.parse(s), i)


class Db:
    def __init__(self, rdb: Valkey):
        self.rdb: Valkey = rdb
        self._pipeline: None | Pipeline = None

    @property
    def pipeline(self) -> Pipeline:
        if self._pipeline is None:
            self._pipeline = self.rdb.pipeline()
        return self._pipeline

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.commit()

    def insert_pipeline(self, cpe: CPE, skip_prod_version=True):
        words: set[str] = set()
        cpe_str = cpe.to_cpe_str(strip_prod_version=skip_prod_version)

        self.pipeline.sadd(Db.vendor_key(cpe.normalized_vendor), cpe_str)
        self.pipeline.sadd(Db.product_key(cpe.normalized_product), cpe_str)

        words.update(cpe.tokenize_vendor())
        words.update(cpe.tokenize_product())
        if not skip_prod_version:
            words.update(cpe.tokenize_version())
        words.update(cpe.tokenize_category())

        for word in words:
            self.pipeline.sadd(Db.word_key(word), cpe_str)
            # compatibility layer with old guesser data model
            self._v1_cpe_guesser_word_index(word, cpe_str)

    @staticmethod
    def word_key(word: str) -> str:
        return f"w:{word.lower()}"

    @staticmethod
    def vendor_key(vendor: str, normalize=False) -> str:
        if normalize:
            vendor = CPE.normalize_tokenized_str(iter(tokenize_text_lower(vendor)))
        return f"vendor:{vendor.lower()}"

    @staticmethod
    def product_key(product: str, normalize=False) -> str:
        if normalize:
            product = CPE.normalize_tokenized_str(iter(tokenize_text_lower(product)))
        return f"product:{product.lower()}"

    def _v1_cpe_guesser_word_index(self, word: str, cpe_str: str):
        self.pipeline.zadd(self.v1_word_rank_key(word), {cpe_str: 1}, incr=True)
        self.pipeline.zadd(self.v1_rank_key(), {cpe_str: 1}, incr=True)

    @staticmethod
    def v1_rank_key() -> str:
        return "rank:cpe"

    @staticmethod
    def v1_word_rank_key(word: str) -> str:
        return f"s:{word.lower()}"

    def _v1_word_score(self, word, cpe):
        score = self.rdb.zscore(self.v1_word_rank_key(word), cpe)
        return score or 0

    def _v1_rank_score(self, cpe):
        score = self.rdb.zscore(self.v1_rank_key(), cpe)
        return score or 0

    def v1_guess_cpe(
        self, words: list[str], limit: int | None = None
    ) -> list[tuple[int, str]]:
        k = []
        for keyword in words:
            k.append(self.word_key(keyword))

        if not k:
            return []

        result = self.rdb.sinter(*k)
        if not result:
            return []

        ranked = []
        lowered_words = [word.lower() for word in words]

        for cpe in result:  # ty:ignore[not-iterable]
            search_score = sum(self._v1_word_score(word, cpe) for word in lowered_words)
            rank_score = self._v1_rank_score(cpe)
            total_score = search_score + rank_score
            ranked.append((total_score, rank_score, cpe))

        r = [(total_score, cpe) for total_score, _, cpe in sorted(ranked, reverse=True)]

        if limit:
            r = r[:limit]

        return r

    def search_vendor_exact(self, vendor: str, exact=False):
        return self.rdb.smembers(self.vendor_key(vendor, normalize=True))

    def search_by_vendor_best(self, vendor: str) -> set[CPE]:
        """
        We try to do our best to get the more relevant CPEs based
        on a given vendor name.

        1. we first try a direct vendor match
        2. we fallback to a broader research based on tokens
        """

        # search by exact vendor
        out: set[str] = set(self.rdb.smembers(Db.vendor_key(vendor, normalize=True)))  # ty:ignore[invalid-argument-type]

        # we find by exact vendor so we can return
        if len(out) > 0:
            return set(map_str_to_cpe(out))

        # search by joined vendor name
        out: set[str] = set(
            self.rdb.smembers(Db.vendor_key(TOKENIZE_RE.sub("", vendor)))  # ty:ignore[invalid-argument-type]
        )

        if len(out) > 0:
            return set(map_str_to_cpe(out))

        return self.search_by_vendor_keywords(vendor)

    def search_by_product_best(self, product: str) -> set[CPE]:
        """
        We try to do our best to get the more relevant CPEs based
        on a given product name.

        1. we first try a direct product match
        2. we fallback to a broader research based on tokens
        """

        # search by exact product
        out: set[str] = set(self.rdb.smembers(Db.product_key(product, normalize=True)))  # ty:ignore[invalid-argument-type]

        # we find by exact product so we can return
        if len(out) > 0:
            return set(map_str_to_cpe(out))

        # search by joined product name
        out: set[str] = set(
            self.rdb.smembers(Db.product_key(TOKENIZE_RE.sub("", product)))  # ty:ignore[invalid-argument-type]
        )

        if len(out) > 0:
            return set(map_str_to_cpe(out))

        return self.search_by_product_keywords(product)

    def search_by_product_keywords(self, product: str) -> set[CPE]:
        keywords = set(tokenize_text_lower(product))
        keys = [Db.word_key(word) for word in keywords]
        it = map_str_to_cpe(self.rdb.sunion(keys))  # ty:ignore[invalid-argument-type]

        # We search on global keyword index so we need to post-filter
        # keywords of CPE vendor must be in keyword list
        return set(
            filter(
                lambda cpe: len(set(cpe.tokenize_product()).intersection(keywords)) > 0,
                it,
            )
        )

    def search_by_vendor_keywords(self, vendor: str) -> set[CPE]:
        keywords = set(tokenize_text_lower(vendor))
        keys = [Db.word_key(word) for word in keywords]
        it = map_str_to_cpe(self.rdb.sunion(keys))  # ty:ignore[invalid-argument-type]

        # We search on global keyword index so we need to post-filter
        # keywords of CPE vendor must be in keyword list
        return set(
            filter(
                lambda cpe: len(set(cpe.tokenize_vendor()).intersection(keywords)) > 0,
                it,
            )
        )

    def search_abritrary_text(
        self,
        text: str,
        vendor: str | None = None,
        product: str | None = None,
        limit: int | None = 10,
        # vendor is often short so more chances to be exact
        try_exact_vendor=True,
        # product may contain version information
        try_exact_product=False,
    ) -> list[tuple[int, str]]:

        if len(text) == 0:
            if vendor is not None and product is not None:
                text = f"{vendor} {product}"
            elif vendor is not None:
                text = f"{vendor}"
            elif product is not None:
                text = f"{product}"
            else:
                return []

        tokens = tokenize_text(text)

        # we try to find chains of words starting with uppercase
        # it helps finding potential product/vendor names
        for chain in find_upper_keywords_chains(tokens):
            # we append the chain to the list of tokens
            # Ex: ["Red", "Hat"] would become "RedHat"
            tokens.append("".join(chain))

        low_keywords = dict()

        # store keywords and their position
        for i, tok in enumerate(map(lambda tok: tok.lower(), tokens)):
            if tok not in low_keywords:
                low_keywords[tok] = set()
            low_keywords[tok].add(i)

        cpes: dict[CPE, int] = {}
        if vendor is not None or product is not None:
            vendor_cpes = set()
            prod_cpes = set()

            if vendor is not None:
                if try_exact_vendor:
                    vendor_cpes = self.search_by_vendor_best(vendor)
                else:
                    vendor_cpes = self.search_by_vendor_keywords(vendor)

            if product is not None:
                if try_exact_product:
                    prod_cpes = self.search_by_product_best(product)
                else:
                    prod_cpes = self.search_by_product_keywords(product)

            if len(vendor_cpes) > 0 and len(prod_cpes) > 0:
                cpes.update({cpe: 10 for cpe in vendor_cpes.intersection(prod_cpes)})
            else:
                cpes.update({cpe: 10 for cpe in vendor_cpes.union(prod_cpes)})

            # we want to search by vendor / product yet we haven't found
            # anything given these restrictive criteria, we should give
            # up the search otherwise we are likely returning FPs
            if len(cpes) == 0:
                return []

        # if cpes is empty we fallback to text analysis
        if len(low_keywords) > 0:
            for cpe in map_str_to_cpe(
                self.rdb.sunion([Db.word_key(k) for k in low_keywords])  # ty:ignore[invalid-argument-type]
            ):
                if cpe not in cpes:
                    cpes[cpe] = 0

        for cpe, score in cpes.items():
            tok_vendor = list(cpe.tokenize_vendor())
            tok_product = list(cpe.tokenize_product())

            if is_tokenized_full_match(low_keywords, tok_vendor):
                score += 15
            elif is_tokenized_full_match(low_keywords, ["".join(tok_vendor)]):
                score += 15

            if is_tokenized_full_match(low_keywords, tok_product):
                score += 10
            elif is_tokenized_full_match(low_keywords, ["".join(tok_product)]):
                score += 10

            for k, vendor_kw in enumerate(tok_vendor[:2]):
                if vendor_kw in low_keywords:
                    score += 2 - min(k, 2)

            for k, prod_kw in enumerate(tok_product[:4]):
                if prod_kw in low_keywords:
                    score += 4 - min(k, 4)

            for tc in cpe.tokenize_category():
                if tc in low_keywords:
                    score += 3
                    # count category only once
                    break

            cpes[cpe] = score

        results = sorted(filter(lambda x: x[1] > 0, cpes.items()), key=lambda x: -x[1])
        if limit is not None:
            results = results[:limit]
        # we return the same format as v1
        return list(map(lambda x: (x[1], x[0].to_cpe_str()), results))

    def commit(self):
        self.pipeline.execute()
        self._pipeline = None
