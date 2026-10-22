from io import BytesIO

from openpyxl import Workbook

HEADERS = ("Nome", "Unidade", "Telefone", "E-mail")


def build_xlsx(
    *lines: tuple[object, ...], headers: tuple[object, ...] = HEADERS
) -> bytes:
    """An .xlsx file with `headers` in the first row and `lines` below it."""
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(list(headers))
    for line in lines:
        worksheet.append(list(line))
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
