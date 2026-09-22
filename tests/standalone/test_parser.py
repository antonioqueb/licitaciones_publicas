import importlib.util
import io
import unittest
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('lp_parser', ROOT / 'parser.py')
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
HEADERS = ['Núm.', 'Partida específica', 'Clave CUCoP+', 'Descripción CUCoP+',
           'Descripción detallada', 'Unidad de medida', 'Cantidad solicitada']
ROW = [1, 21601.0, '21601-0028', 'FIBRA', 'Fibra verde\n"Limpieza"', 'PIEZA', 4000]
IDENTIFIER = 'IA-50-GYR-050GYR032-N-89-2026'


def workbook(headers=HEADERS, rows=None, blank_rows=0):
    wb = openpyxl.Workbook()
    for _ in range(blank_rows):
        wb.active.append([None])
    wb.active.append(headers)
    for row in ([ROW] if rows is None else rows):
        wb.active.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def read(data, filename=IDENTIFIER + '.xlsx', **kwargs):
    reader = parser.WorkbookReader(data, filename, **kwargs)
    try:
        return reader.rows()
    finally:
        reader.close()


class TestParser(unittest.TestCase):
    def test_real_format_description_preserved(self):
        row = read(workbook())[0]
        self.assertEqual(row['partida_especifica'], '21601')
        self.assertEqual(row['descripcion_detallada'], ROW[4])
        self.assertEqual(row['cantidad'], 4000)

    def test_fifty_synthetic_rows(self):
        rows = [[n, 21601, f'21601-{n:04}', 'FIBRA', f'Fibra {n}', 'PIEZA', n * 10] for n in range(1, 51)]
        self.assertEqual(len(read(workbook(rows=rows))), 50)

    def test_headers_second_row(self):
        self.assertEqual(len(read(workbook(blank_rows=1))), 1)

    def test_headers_fifth_row(self):
        self.assertEqual(len(read(workbook(blank_rows=4))), 1)

    def test_headers_sixth_row_rejected(self):
        with self.assertRaisesRegex(parser.ImportValidationError, 'primeras 5'):
            read(workbook(blank_rows=5))

    def test_blank_trailing_rows_ignored(self):
        self.assertEqual(len(read(workbook(rows=[ROW, [None] * 7, [''] * 7]))), 1)

    def test_same_cucop_different_description(self):
        other = list(ROW)
        other[0], other[4] = 2, 'Otra fibra'
        self.assertEqual(len(read(workbook(rows=[ROW, other]))), 2)

    def test_duplicate_identical_collapsed(self):
        self.assertEqual(len(read(workbook(rows=[ROW, ROW]))), 1)

    def test_duplicate_conflicting_rejected(self):
        other = list(ROW)
        other[-1] = 8000
        with self.assertRaisesRegex(parser.ImportValidationError, 'contradictorios'):
            read(workbook(rows=[ROW, other]))

    def test_open_purchase_range(self):
        data = workbook(HEADERS[:-1] + ['Cantidad mínima', 'Cantidad máxima'], [ROW[:-1] + [10, 30]])
        row = read(data)[0]
        self.assertEqual((row['cantidad'], row['cantidad_min'], row['cantidad_max']), (30, 10, 30))

    def test_zero_quantity_does_not_fall_back(self):
        data = workbook(HEADERS + ['Cantidad mínima', 'Cantidad máxima'], [ROW[:-1] + [0, 0, 30]])
        self.assertEqual(read(data)[0]['cantidad'], 0)

    def test_invalid_range(self):
        with self.assertRaisesRegex(parser.ImportValidationError, 'mínima mayor'):
            read(workbook(HEADERS[:-1] + ['Cantidad mínima', 'Cantidad máxima'], [ROW[:-1] + [30, 10]]))

    def test_missing_quantity_columns(self):
        with self.assertRaisesRegex(parser.ImportValidationError, 'Cantidad solicitada'):
            read(workbook(HEADERS[:-1], [ROW[:-1]]))

    def test_missing_required_value(self):
        row = list(ROW)
        row[4] = None
        with self.assertRaisesRegex(parser.ImportValidationError, 'Fila 2'):
            read(workbook(rows=[row]))

    def test_uncomputed_quantity_formula(self):
        row = list(ROW)
        row[-1] = '=2*3'
        with self.assertRaises(parser.ImportValidationError):
            read(workbook(rows=[row]))

    def test_thousands_string(self):
        row = list(ROW)
        row[-1] = '4,000.50'
        self.assertEqual(read(workbook(rows=[row]))[0]['cantidad'], 4000.5)

    def test_empty_workbook_rejected(self):
        with self.assertRaisesRegex(parser.ImportValidationError, 'no contiene registros'):
            read(workbook(rows=[]))

    def test_invalid_number(self):
        for value in [-1, 'bad', float('nan'), float('inf'), True]:
            with self.subTest(value=value), self.assertRaises(parser.ImportValidationError):
                parser.number(value)

    def test_code_preserves_leading_zero_string(self):
        self.assertEqual(parser.code('021601'), '021601')
        self.assertEqual(parser.code(21601.0), '21601')
        self.assertEqual(parser.code(None), '')
        for value in [True, 3.14, float('nan')]:
            with self.assertRaises(parser.ImportValidationError):
                parser.code(value)

    def test_invalid_correlative(self):
        for value in (0, 1.2):
            row = list(ROW)
            row[0] = value
            with self.assertRaises(parser.ImportValidationError):
                read(workbook(rows=[row]))

    def test_duplicate_headers(self):
        with self.assertRaisesRegex(parser.ImportValidationError, 'duplicados'):
            read(workbook(HEADERS + ['Cantidad'], [ROW + [4000]]))

    def test_invalid_file(self):
        for content, name in [(b'not zip', 'bad.xlsx'), (workbook(), 'bad.xls')]:
            with self.assertRaises(parser.ImportValidationError):
                read(content, name)

    def test_limits(self):
        previous = parser.WorkbookReader.MAX_BYTES
        parser.WorkbookReader.MAX_BYTES = 10
        try:
            with self.assertRaises(parser.ImportValidationError):
                read(workbook())
        finally:
            parser.WorkbookReader.MAX_BYTES = previous
        previous = parser.WorkbookReader.MAX_ROWS
        parser.WorkbookReader.MAX_ROWS = 1
        try:
            with self.assertRaisesRegex(parser.ImportValidationError, '50,000'):
                read(workbook(rows=[ROW, ROW]))
        finally:
            parser.WorkbookReader.MAX_ROWS = previous

    def test_filename_identifier(self):
        for prefix in ['IA', 'LA', 'LO', 'IO', 'AD', 'LI']:
            identifier = IDENTIFIER.replace('IA-', prefix + '-')
            reader = parser.WorkbookReader(workbook(), 'export_' + identifier + ' (1).xlsx')
            try:
                self.assertEqual(reader.detect_identifier_from_filename(), identifier)
                self.assertEqual(parser.identifier_parts(identifier)['ordenamiento_legal'], 'LOPSRM' if prefix in ('LO', 'IO') else 'LAASSP')
            finally:
                reader.close()
        reader = parser.WorkbookReader(workbook(), 'sin-identificador.xlsx')
        self.assertIsNone(reader.detect_identifier_from_filename())
        reader.close()

    def test_identifier_invalid(self):
        with self.assertRaises(parser.ImportValidationError):
            parser.identifier_parts('incorrecto')

    def test_mexico_timezone(self):
        self.assertEqual(parser.portal_datetime('21/09/2026 09:00', 'America/Mexico_City'), '2026-09-21 15:00:00')
        self.assertEqual(parser.portal_datetime(datetime(2026, 9, 21, 9), 'America/Mexico_City'), '2026-09-21 15:00:00')
        self.assertFalse(parser.portal_datetime(None, 'America/Mexico_City'))
        with self.assertRaises(parser.ImportValidationError):
            parser.portal_datetime('no es fecha', 'America/Mexico_City')
        with self.assertRaises(parser.ImportValidationError):
            read(workbook(), tz_name='bad/timezone')

    def test_listado_headers_tolerant(self):
        headers = ['NUMERO_PROCEDIMIENTO', 'Nombre publicado', 'Unidad compradora', 'Estatus', 'Tipo de contratación', 'Fecha de apertura']
        data = workbook(headers, [[IDENTIFIER, 'Licitación de limpieza', 'UC México', 'Vigente', 'Adquisiciones', '21/09/2026 09:00']])
        row = read(data)[0]
        self.assertEqual(row['tipo_codigo'], 'ADQ')
        self.assertEqual(row['unidad_codigo'], '050GYR032')
        self.assertEqual(row['fecha_apertura'], '2026-09-21 15:00:00')
        self.assertNotIn('fecha_fallo', row)
        self.assertNotIn('codigo_expediente', row)

    def test_listado_unknown_type(self):
        headers = ['Número de procedimiento', 'Nombre', 'Unidad compradora', 'Estatus', 'Tipo de contratación']
        with self.assertRaisesRegex(parser.ImportValidationError, 'Tipo de contratación'):
            read(workbook(headers, [[IDENTIFIER, 'X', 'UC', 'Nuevo', 'desconocido']]))

    def test_business_key_delimiter_safe(self):
        first = {'partida_especifica': 'a|b', 'clave_cucop': 'c', 'descripcion_detallada': 'd'}
        other = {'partida_especifica': 'a', 'clave_cucop': 'b|c', 'descripcion_detallada': 'd'}
        self.assertNotEqual(parser.business_key(first), parser.business_key(other))

    def test_diff_idempotence(self):
        rows = [{'identificador': 'A', 'fecha': '2026-09-21'}]
        first = parser.diff_rows(rows, {})
        second = parser.diff_rows(rows, {'A': rows[0]}, ['A'])
        self.assertEqual(len(first['nuevos']), 1)
        self.assertEqual([len(second[k]) for k in ('nuevos', 'cambios', 'sin_cambios', 'gone')], [0, 0, 1, 0])

    def test_diff_preserves_internal_state(self):
        current = {'A': {'identificador': 'A', 'fecha': 'antes', 'state': 'descartado'}}
        diff = parser.diff_rows([{'identificador': 'A', 'fecha': 'despues'}], current)
        self.assertEqual(list(diff['cambios'][0]['diff']), ['fecha'])
        self.assertEqual(current['A']['state'], 'descartado')

    def test_gone_only_previous_snapshot(self):
        current = {k: {'identificador': k} for k in ('A', 'B', 'C')}
        diff = parser.diff_rows([current['A']], current, ['A', 'B'])
        self.assertEqual([r['key'] for r in diff['gone']], ['B'])

    def test_reappearance_is_change(self):
        current = {'A': {'identificador': 'A', 'sigue_apareciendo': False}}
        diff = parser.diff_rows([{'identificador': 'A', 'sigue_apareciendo': True}], current)
        self.assertEqual(len(diff['cambios']), 1)

    def test_diff_duplicate_rejected(self):
        with self.assertRaises(parser.ImportValidationError):
            parser.diff_rows([{'identificador': 'A'}, {'identificador': 'A'}], {})

    def test_117_synthetic_not_official_fixture(self):
        headers = ['Número de procedimiento', 'Nombre', 'Unidad compradora', 'Estatus', 'Tipo de contratación']
        rows = [[f'LA-50-GYR-050GYR032-N-{n}-2026', f'Prueba {n}', 'UC', 'Vigente', 'ADQ'] for n in range(1, 118)]
        self.assertEqual(len(read(workbook(headers, rows))), 117)


if __name__ == '__main__':
    unittest.main()
