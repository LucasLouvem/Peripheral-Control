"""Parser de report descriptors HID.

Formato do item curto (HID 1.11, 6.2.2.2): o primeiro byte traz ``bSize`` nos bits
0-1 (3 significa 4 bytes), ``bType`` nos bits 2-3 (0 Main, 1 Global, 2 Local) e
``bTag`` nos bits 4-7. O prefixo ``0xFE`` marca um item longo.
"""

from dataclasses import dataclass

from .errors import DescriptorError

_MAIN = {0x8: "input", 0x9: "output", 0xB: "feature"}
_COLLECTION, _END_COLLECTION = 0xA, 0xC
_G_USAGE_PAGE, _G_REPORT_SIZE, _G_REPORT_ID, _G_REPORT_COUNT = 0x0, 0x7, 0x8, 0x9
_LONG_ITEM = 0xFE


@dataclass(frozen=True)
class ReportField:
    """Um item Input/Output/Feature, com o total de bits que ele ocupa."""

    kind: str
    report_id: int
    bits: int
    usage_page: int | None


@dataclass(frozen=True)
class ParsedDescriptor:
    fields: tuple[ReportField, ...]
    collection_pages: tuple[int, ...]

    def payload_sizes(self, kind: str) -> dict[int, int]:
        """Bytes de dados por Report ID (sem o byte do ID), arredondando para cima."""
        bits: dict[int, int] = {}
        for item in self.fields:
            if item.kind == kind:
                bits[item.report_id] = bits.get(item.report_id, 0) + item.bits
        return {rid: (total + 7) // 8 for rid, total in bits.items()}

    def wire_size(self, kind: str, report_id: int) -> int | None:
        """Bytes no fio: dados mais 1 para o Report ID, quando ele existe."""
        size = self.payload_sizes(kind).get(report_id)
        if size is None:
            return None
        return size + (1 if report_id else 0)

    def pages_of(self, kind: str, report_id: int) -> set[int]:
        return {
            item.usage_page
            for item in self.fields
            if item.kind == kind and item.report_id == report_id and item.usage_page is not None
        }


def parse(data: bytes) -> ParsedDescriptor:
    """Decodifica ``data``; levanta ``DescriptorError`` se estiver truncado ou inválido."""
    fields: list[ReportField] = []
    pages: list[int] = []
    usage_page = 0
    report_size = report_count = report_id = 0
    depth = 0
    top_page: int | None = None
    pos = 0
    while pos < len(data):
        prefix = data[pos]
        if prefix == _LONG_ITEM:
            if pos + 2 >= len(data):
                raise DescriptorError(f"item longo truncado em {pos}")
            pos += 3 + data[pos + 1]
            if pos > len(data):
                raise DescriptorError("dados do item longo ultrapassam o descritor")
            continue
        size = prefix & 0x03
        size = 4 if size == 3 else size
        item_type = (prefix >> 2) & 0x03
        tag = prefix >> 4
        if item_type == 3:
            raise DescriptorError(f"tipo de item reservado no byte {pos}")
        if pos + 1 + size > len(data):
            raise DescriptorError(f"item truncado no byte {pos}")
        value = int.from_bytes(data[pos + 1 : pos + 1 + size], "little")
        pos += 1 + size

        if item_type == 1:  # Global
            if tag == _G_USAGE_PAGE:
                usage_page = value
            elif tag == _G_REPORT_SIZE:
                report_size = value
            elif tag == _G_REPORT_ID:
                report_id = value
            elif tag == _G_REPORT_COUNT:
                report_count = value
        elif item_type == 0:  # Main
            if tag == _COLLECTION:
                if depth == 0:
                    top_page = usage_page
                    pages.append(usage_page)
                depth += 1
            elif tag == _END_COLLECTION:
                if depth == 0:
                    raise DescriptorError("End Collection sem Collection correspondente")
                depth -= 1
                if depth == 0:
                    top_page = None
            elif tag in _MAIN:
                fields.append(
                    ReportField(_MAIN[tag], report_id, report_size * report_count, top_page)
                )
    if depth != 0:
        raise DescriptorError("Collection sem End Collection")
    return ParsedDescriptor(tuple(fields), tuple(pages))
