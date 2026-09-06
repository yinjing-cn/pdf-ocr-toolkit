"""Parser stage: the :class:`BaseParser` contract and shared extraction tools.

Concrete parsers subclass :class:`BaseParser`, register themselves with
:func:`pdf_ocr_toolkit.core.registry.register_parser` and implement
:meth:`BaseParser.parse`.  A toolkit of small, well-tested helpers (regex
search, keyword anchors, money/date normalisation, line scanning) is provided
so that new document types can be supported in a few dozen lines.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from pdf_ocr_toolkit.core.logging import get_logger
from pdf_ocr_toolkit.pipeline.loader import Document

logger = get_logger(__name__)

#: Contact-style label lines (``Attn: …``, ``Tel: …``) are part of an address
#: block rather than field delimiters, so block scanning continues across them.
CONTACT_LINE = re.compile(
    r"^\s*(?:attn|attention|tel|phone|fax|e?-?mail|contact|delivery\s+contact)\b",
    re.IGNORECASE,
)


@dataclass
class LineItem:
    """One row of a document's detail table."""

    description: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "description": self.description,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "amount": self.amount,
        }
        data.update(self.extra)
        return data


@dataclass
class ParseResult:
    """Structured output of a parser run."""

    document_type: str
    fields: Dict[str, Any] = field(default_factory=dict)
    line_items: List[LineItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "fields": self.fields,
            "line_items": [item.to_dict() for item in self.line_items],
            "warnings": list(self.warnings),
        }


class BaseParser(abc.ABC):
    """Abstract base class for document parsers.

    Subclasses set the class-level metadata and implement :meth:`parse`.
    """

    #: Human-readable document label, e.g. "Generic Invoice".
    label: str = "Document"
    #: One-line description used by CLI/API help.
    description: str = ""

    def __init__(self) -> None:
        self.logger = get_logger(f"{__name__}.{type(self).__name__}")

    # ------------------------------------------------------------------ #
    # Contract
    # ------------------------------------------------------------------ #
    @abc.abstractmethod
    def parse(self, document: Document) -> ParseResult:
        """Extract structured fields and line items from ``document``."""

    # ------------------------------------------------------------------ #
    # Regex helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def search(pattern: str, text: str, group: int | str = 1, flags: int = 0) -> Optional[str]:
        """Return the first regex match group, or ``None`` when not found."""
        match = re.search(pattern, text, flags)
        if not match:
            return None
        try:
            return match.group(group)
        except (IndexError, re.error):  # pragma: no cover - defensive
            return None

    @staticmethod
    def find_all(pattern: str, text: str, flags: int = 0) -> List[re.Match]:
        """Return every regex match in ``text``."""
        return list(re.finditer(pattern, text, flags))

    # ------------------------------------------------------------------ #
    # Value normalisation
    # ------------------------------------------------------------------ #
    @staticmethod
    def to_money(value: str | None) -> Optional[float]:
        """Normalise a money string like ``'$1,234.50'`` to ``1234.50``."""
        if value is None:
            return None
        cleaned = value.replace(",", "").replace("$", "").replace("￥", "").strip()
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)
        if not cleaned or cleaned in {"-", ".", "-."}:
            return None
        try:
            return round(float(cleaned), 2)
        except ValueError:
            return None

    @staticmethod
    def to_number(value: str | None) -> Optional[float]:
        """Normalise an integer/decimal string, tolerating commas."""
        if value is None:
            return None
        cleaned = value.replace(",", "").strip()
        try:
            number = float(cleaned)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number

    @staticmethod
    def normalise_date(value: str | None) -> Optional[str]:
        """Normalise common date spellings to ISO ``YYYY-MM-DD``.

        Accepts ``2025-01-31``, ``2025/1/31``, ``Jan 31, 2025`` and
        ``31-Jan-2025``.  Returns ``None`` if nothing recognisable is found.
        """
        if not value:
            return None
        text = value.strip()

        iso = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
        if iso:
            year, month, day = iso.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        months = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        month_first = re.search(
            r"([A-Za-z]{3,})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", text
        )
        if month_first:
            mon, day, year = month_first.groups()
            code = months.get(mon[:3].lower())
            if code:
                return f"{int(year):04d}-{code}-{int(day):02d}"

        day_first = re.search(
            r"(\d{1,2})[- ]([A-Za-z]{3,})[a-z]*\.?[- ](\d{4})", text
        )
        if day_first:
            day, mon, year = day_first.groups()
            code = months.get(mon[:3].lower())
            if code:
                return f"{int(year):04d}-{code}-{int(day):02d}"
        return None

    # ------------------------------------------------------------------ #
    # Line-oriented scanning
    # ------------------------------------------------------------------ #
    @staticmethod
    def lines_of(text: str) -> List[str]:
        """Split ``text`` into stripped, non-empty lines."""
        return [line.strip() for line in text.splitlines() if line.strip()]

    def find_line(self, lines: Sequence[str], *keywords: str) -> Optional[int]:
        """Return the index of the first line containing *all* keywords.

        Matching is case-insensitive.
        """
        patterns = [re.compile(rf"\b{re.escape(kw.lower())}\b") for kw in keywords]
        for index, line in enumerate(lines):
            line_lower = line.lower()
            if all(pattern.search(line_lower) for pattern in patterns):
                return index
        return None

    def value_after_label(
        self,
        lines: Sequence[str],
        *keywords: str,
        separators: str = r"[:：]\s*",
    ) -> Optional[str]:
        """Return the value following a label such as ``Invoice No: INV-001``.

        The label line must contain all ``keywords``; the text after the
        separator is returned.  If the label sits alone on its line, the
        *next* non-label line is returned instead.
        """
        index = self.find_line(lines, *keywords)
        if index is None:
            return None
        line = lines[index]
        match = re.search(separators + r"(.+)$", line)
        if match:
            value = match.group(1).strip()
            if value:
                return value
        # Value on the following line (e.g. "Bill To:\nAcme Corp").
        for following in lines[index + 1: index + 4]:
            if not re.search(r"[:：]", following) and not following.lower().endswith(
                ("date", "no", "number", "to", "address")
            ):
                return following
        return None

    def block_after_label(
        self,
        lines: Sequence[str],
        *keywords: str,
        max_lines: int = 6,
    ) -> List[str]:
        """Collect up to ``max_lines`` lines that follow a label line.

        Collection stops at the next label-style line (containing a colon),
        a table-like line (3+ numeric tokens) or the end of the document.
        """
        index = self.find_line(lines, *keywords)
        if index is None:
            return []
        collected: List[str] = []
        header_words = r"\b(description|qty|quantity|unit\s*price|amount|item|sku|goods)\b"
        for line in lines[index + 1: index + 1 + max_lines]:
            # Contact lines belong to the address block; keep collecting.
            if CONTACT_LINE.match(line):
                collected.append(line)
                continue
            if re.search(r"[:：]", line):
                break
            if re.search(header_words, line, re.IGNORECASE):
                break
            numeric_tokens = len(re.findall(r"\d+(?:\.\d+)?", line))
            if numeric_tokens >= 3:
                break
            collected.append(line)
        return collected

    def money_after_label(self, lines: Sequence[str], *keywords: str) -> Optional[float]:
        """Return the money value following a label, or ``None``."""
        raw = self.value_after_label(lines, *keywords)
        if raw is None:
            return None
        money = self.to_money(raw)
        if money is not None:
            return money
        # The value may share the line after unrelated words; grab the last
        # money-looking token.
        candidates = re.findall(r"[\d,]+\.\d{2}", raw)
        return self.to_money(candidates[-1]) if candidates else None

    # ------------------------------------------------------------------ #
    # Convenience for concrete parsers
    # ------------------------------------------------------------------ #
    def require(self, result: ParseResult, field_name: str, value: Any) -> None:
        """Record ``value`` into ``result.fields`` with a warning when empty."""
        if value in (None, "", []):
            result.warnings.append(f"Field '{field_name}' could not be extracted.")
            self.logger.warning("Could not extract field '%s'.", field_name)
        result.fields[field_name] = value
