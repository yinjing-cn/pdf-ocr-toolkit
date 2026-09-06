"""Built-in parser for generic commercial invoices.

Extracts: invoice number, invoice date, due date, seller (issuer) and buyer
(bill-to) parties, currency, line-item table (description / qty / unit price /
amount), subtotal, tax rate, tax amount and grand total.

The parser deliberately relies on common English labels and a tolerant line
regex rather than fixed coordinates, so it works on both text-layer PDFs and
OCR output with minor layout variations.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pdf_ocr_toolkit.core.logging import get_logger
from pdf_ocr_toolkit.core.registry import register_parser
from pdf_ocr_toolkit.pipeline.base_parser import CONTACT_LINE, BaseParser, LineItem, ParseResult
from pdf_ocr_toolkit.pipeline.loader import Document

logger = get_logger(__name__)

# A detail row:  <description...>  <qty>  <unit price>  <amount>
# Trailing-number anchoring keeps this robust whether the source preserves
# wide column gaps (raw text) or collapses them (pdfplumber output).
# e.g. "Wireless Mouse (Demo Model) 10 25.00 250.00"
_ITEM_ROW = re.compile(
    r"^(?P<desc>.+?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?P<price>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*$"
)

_DATE = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|[A-Za-z]{3,}\.?\s+\d{1,2},?\s+\d{4}")
_CURRENCY = re.compile(r"\b(USD|CNY|EUR|GBP|JPY)\b", re.IGNORECASE)


@register_parser("invoice")
class GenericInvoiceParser(BaseParser):
    """Parser for generic invoices (demo data: fictional 'Demo Trading Co')."""

    label = "Generic Invoice"
    description = "Generic commercial invoice: number, parties, line items, tax and total."

    def parse(self, document: Document) -> ParseResult:
        result = ParseResult(document_type="invoice")
        text = document.full_text
        lines = self.lines_of(text)

        result.fields["_title"] = "Invoice"

        # --- Header scalars ---
        self.require(result, "invoice_number", self.value_after_label(lines, "invoice", "no"))
        self.require(
            result,
            "invoice_date",
            self.normalise_date(self.value_after_label(lines, "invoice", "date")
                                 or self.value_after_label(lines, "date")),
        )
        self.require(
            result,
            "due_date",
            self.normalise_date(self.value_after_label(lines, "due", "date")
                                 or self.value_after_label(lines, "payment", "due")),
        )
        currency_match = _CURRENCY.search(text)
        result.fields["currency"] = currency_match.group(1).upper() if currency_match else "USD"

        # --- Parties ---
        seller, seller_addr = self._extract_seller(lines)
        self.require(result, "seller", seller)
        result.fields["seller_address"] = seller_addr

        buyer_block = self.block_after_label(lines, "bill", "to") or self.block_after_label(lines, "buyer")
        self.require(result, "buyer", buyer_block[0] if buyer_block else None)
        result.fields["buyer_address"] = "; ".join(buyer_block[1:]) if len(buyer_block) > 1 else ""

        # --- Line items ---
        result.line_items = self._extract_items(lines)
        if not result.line_items:
            result.warnings.append("No line items detected on the invoice.")

        # --- Totals ---
        self.require(result, "subtotal", self._money_line(lines, r"^\s*subtotal\b"))
        self.require(result, "tax_rate", self._tax_rate(lines))
        self.require(result, "tax_amount", self._money_line(lines, r"^\s*tax(?!\s*rate)"))
        self.require(result, "total_amount", self._money_line(lines, r"^\s*(?:grand\s*)?total\b"))

        # Cross-check: sum of line amounts should match the declared subtotal.
        computed = round(sum(item.amount or 0.0 for item in result.line_items), 2)
        declared_subtotal = result.fields.get("subtotal")
        if declared_subtotal and computed and abs(computed - float(declared_subtotal)) > 0.05:
            result.warnings.append(
                f"Sum of line amounts ({computed}) differs from declared subtotal "
                f"({declared_subtotal})."
            )
        return result

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #
    def _extract_seller(self, lines: List[str]) -> tuple[Optional[str], str]:
        """The issuer is the letterhead: lines before the first field label."""
        head: List[str] = []
        for line in lines:
            if CONTACT_LINE.match(line):
                head.append(line)  # phone/fax lines are part of the letterhead
                continue
            if re.search(r"[:：]", line) or re.search(r"\binvoice\b", line, re.IGNORECASE):
                break
            head.append(line)
        if not head:
            return None, ""
        return head[0], "; ".join(head[1:])

    def _extract_items(self, lines: List[str]) -> List[LineItem]:
        items: List[LineItem] = []
        for line in lines:
            # Label lines ("Invoice No: …", "Tel: …") are never item rows.
            if ":" in line or "：" in line:
                continue
            match = _ITEM_ROW.match(line)
            if not match:
                continue
            desc = match.group("desc").strip()
            # Guard: never treat label/table-header lines as items.
            if re.search(r"\b(subtotal|total|tax|description|qty|quantity)\b", desc, re.IGNORECASE):
                continue
            # A real description contains alphabetic characters.
            if not re.search(r"[A-Za-z]", desc):
                continue
            items.append(
                LineItem(
                    description=desc,
                    quantity=self.to_number(match.group("qty")),
                    unit_price=self.to_money(match.group("price")),
                    amount=self.to_money(match.group("amount")),
                )
            )
        return items

    def _money_line(self, lines: List[str], pattern: str) -> Optional[float]:
        """Return the last money token on the first line matching ``pattern``.

        Both label-style lines (``Subtotal: 1,234.50``) and column-style
        lines (``Tax        112.05``) are handled.
        """
        for line in lines:
            if not re.search(pattern, line, re.IGNORECASE):
                continue
            numbers = re.findall(r"[\d,]+\.\d{2}", line)
            if numbers:
                return self.to_money(numbers[-1])
            after = line.split(":", 1)[-1]
            return self.to_money(after)
        return None

    def _tax_rate(self, lines: List[str]) -> Optional[str]:
        for line in lines:
            if re.search(r"tax\s*rate", line, re.IGNORECASE):
                match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
                if match:
                    return f"{match.group(1)}%"
        return None
