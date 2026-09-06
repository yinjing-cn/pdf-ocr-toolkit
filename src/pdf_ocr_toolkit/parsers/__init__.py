"""Built-in parsers.

Importing this package triggers the ``@register_parser`` decorators in the
parser modules, registering the shipped parsers with the global registry.
Third-party parsers follow exactly the same pattern.
"""

from pdf_ocr_toolkit.parsers import delivery_note, invoice  # noqa: F401

__all__ = ["invoice", "delivery_note"]
