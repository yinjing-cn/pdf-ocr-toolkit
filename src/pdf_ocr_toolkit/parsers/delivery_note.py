"""Built-in parser for generic delivery notes (送货单 / packing-list style).

Extracts: delivery note number, delivery date, the issuing supplier, the
customer and ship-to address, the receiver (signatory), order reference and
the shipped-item table (description / quantity; unit price when present).

Demo data uses the fictional supplier 'Acme Corp' and fictional customer
'Blue River Cafe'.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pdf_ocr_toolkit.core.registry import register_parser
from pdf_ocr_toolkit.pipeline.base_parser import (
    CONTACT_LINE,
    BaseParser,
    LineItem,
    ParseResult,
)
from pdf_ocr_toolkit.pipeline.loader import Document

# A shipped-item row:  <description...>  <qty>  [unit price]
# e.g. "Ceramic Coffee Cup 250ml      40      4.50"
_ITEM_ROW = re.compile(
    r"^(?P<desc>.+?)\s+(?P<qty>\d+)(?:\s+(?P<price>\d+\.\d+))?\s*$"
)


@register_parser("delivery_note")
class DeliveryNoteParser(BaseParser):
    """Parser for generic delivery notes (fictional demo data only)."""

    label = "Delivery Note"
    description = "Generic delivery note: note number, parties, shipped items and receiver."

    def parse(self, document: Document) -> ParseResult:
        result = ParseResult(document_type="delivery_note")
        lines = self.lines_of(document.full_text)

        result.fields["_title"] = "Delivery Note"

        # --- Header scalars ---
        self.require(
            result,
            "note_number",
            self.value_after_label(lines, "delivery", "note", "no")
            or self.value_after_label(lines, "note", "no"),
        )
        self.require(
            result,
            "delivery_date",
            self.normalise_date(self.value_after_label(lines, "delivery", "date")
                                 or self.value_after_label(lines, "date")),
        )
        self.require(result, "order_reference", self.value_after_label(lines, "order", "ref"))

        # --- Parties ---
        supplier, supplier_addr = self._extract_letterhead(lines)
        self.require(result, "supplier", supplier)
        result.fields["supplier_address"] = supplier_addr

        customer = self.value_after_label(lines, "customer")
        self.require(result, "customer", customer)

        address_lines = self.block_after_label(lines, "ship", "address")
        # The first block line may repeat the customer name; keep the address proper.
        if customer and address_lines and address_lines[0].strip().lower() == str(customer).strip().lower():
            address_lines = address_lines[1:]
        self.require(result, "ship_to_address", "; ".join(address_lines))

        self.require(result, "received_by", self._receiver(lines))

        # --- Items ---
        result.line_items = self._extract_items(lines)
        if not result.line_items:
            result.warnings.append("No shipped items detected on the delivery note.")

        return result

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #
    def _extract_letterhead(self, lines: List[str]) -> tuple[Optional[str], str]:
        """The supplier name/address sit at the top, before the first label.

        The document title (a line containing "delivery note") is skipped.
        """
        head: List[str] = []
        for line in lines:
            if CONTACT_LINE.match(line):
                head.append(line)  # phone/fax lines belong to the letterhead
                continue
            if re.search(r"[:：]", line):
                break
            if re.search(r"delivery\s*note", line, re.IGNORECASE):
                continue
            if head and re.search(r"\b(no|date|ref)\b", line, re.IGNORECASE):
                # Once we reach header meta lines, the letterhead is over.
                break
            head.append(line)
        if not head:
            return None, ""
        return head[0], "; ".join(head[1:])

    def _extract_items(self, lines: List[str]) -> List[LineItem]:
        items: List[LineItem] = []
        for line in lines:
            # Label lines (document numbers, addresses with colons, phone
            # numbers) are never item rows.
            if ":" in line or "：" in line:
                continue
            match = _ITEM_ROW.match(line)
            if not match:
                continue
            desc = match.group("desc").strip()
            if re.search(r"\b(description|qty|quantity|item|goods|shipped)\b", desc, re.IGNORECASE):
                continue
            # A real item description contains alphabetic characters.
            if not re.search(r"[A-Za-z]", desc):
                continue
            price = match.groupdict().get("price")
            items.append(
                LineItem(
                    description=desc,
                    quantity=self.to_number(match.group("qty")),
                    unit_price=self.to_money(price) if price else None,
                    amount=None,
                )
            )
        return items

    def _receiver(self, lines: List[str]) -> Optional[str]:
        """Extract the signatory, tolerating an empty signature line."""
        raw = self.value_after_label(lines, "received", "by") or self.value_after_label(lines, "signed")
        if raw and not re.search(r"[x_\-]{2,}", raw):
            return raw.strip()
        return None
