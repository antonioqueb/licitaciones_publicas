"""Tabular rendering shared by OCA reports and standalone workbook tests."""
import datetime


def table(workbook, name, headers, rows, money_columns=(), percent_columns=()):
    sheet = workbook.add_worksheet(name)
    head = workbook.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': '#FFFFFF', 'text_wrap': True})
    money = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
    percent = workbook.add_format({'num_format': '0.00"%"', 'align': 'right'})
    text = workbook.add_format({'text_wrap': True, 'valign': 'top'})
    date = workbook.add_format({'num_format': 'dd/mm/yyyy'})
    sheet.freeze_panes(1, 0)
    sheet.set_row(0, 30)
    sheet.set_column(0, len(headers) - 1, 20)
    for col, value in enumerate(headers):
        sheet.write_string(0, col, value, head)
    for index, row in enumerate(rows, 1):
        for col, value in enumerate(row):
            if isinstance(value, bool):
                sheet.write_string(index, col, 'Sí' if value else 'No', text)
            elif isinstance(value, (datetime.datetime, datetime.date)):
                sheet.write_datetime(index, col, value, date)
            elif isinstance(value, (float, int)):
                sheet.write_number(index, col, value, percent if col in percent_columns else money if col in money_columns else None)
            else:
                # Explicit strings prevent formulas/URLs embedded in imported descriptions.
                sheet.write_string(index, col, str(value or ''), text)
    sheet.autofilter(0, 0, max(len(rows), 1), len(headers) - 1)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(0)
    return sheet


def costeo(workbook, name, rows):
    return table(workbook, name, ['Empresa', 'Procedimiento', 'Partida', 'Clave CUCoP+', 'Descripción',
        'Cantidad', 'Costo unitario', 'Precio unitario', 'Costo total', 'Precio total', 'Margen %', 'Recargo secundaria %', 'Moneda'],
        rows, money_columns=(6, 7, 8, 9), percent_columns=(10, 11))


def partidas(workbook, name, rows):
    return table(workbook, name, ['Procedimiento', 'Núm.', 'Partida específica', 'Clave CUCoP+', 'Descripción CUCoP+',
        'Descripción detallada', 'Unidad', 'Cantidad', 'Cantidad mínima', 'Cantidad máxima', 'Empresa principal',
        'Empresas secundarias', 'Proveedores', 'Participación', 'Motivo de descarte', 'Sigue apareciendo'], rows)


def checklist(workbook, name, rows):
    return table(workbook, name, ['Empresa', 'Expediente', 'Proveedor', 'Partida', 'Tipo', 'Estado',
        'Fecha de recepción', 'Fecha de vencimiento', 'Bloqueante', 'Archivo'], rows)
