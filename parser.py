"""Pure, side-effect-free ComprasMX reader. Also exercised without an Odoo server."""
import hashlib
import io
import json
import math
import re
import unicodedata
import zipfile
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import openpyxl


class ImportValidationError(ValueError):
    pass


IDENTIFIER = re.compile(r'(?<![A-Z0-9])((?:LA|IA|AD|LO|IO|LI)-\d+-[A-Z0-9]+-[A-Z0-9]+-[NIT]-\d+-\d{4})(?![A-Z0-9])', re.I)
DATE_FIELDS = ('fecha_junta_aclaraciones', 'fecha_limite_preguntas',
               'fecha_entrega_muestras', 'fecha_apertura', 'fecha_fallo')
PARTIDA_FIELDS = ('numero', 'partida_especifica', 'clave_cucop', 'descripcion_cucop',
                  'descripcion_detallada', 'unidad_medida', 'cantidad', 'cantidad_min', 'cantidad_max')
PORTAL_FIELDS = ('identificador', 'nombre_publicado', 'codigo_expediente',
                 'unidad_codigo', 'unidad_nombre', 'entidad_codigo', 'estatus', 'tipo_codigo') + DATE_FIELDS


def norm(value):
    text = unicodedata.normalize('NFKD', str(value if value is not None else ''))
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c)).lower()).strip()


ALIASES = {
    'numero': ('num', 'numero', 'n'),
    'partida_especifica': ('partida especifica',),
    'clave_cucop': ('clave cucop',),
    'descripcion_cucop': ('descripcion cucop',),
    'descripcion_detallada': ('descripcion detallada',),
    'unidad_medida': ('unidad de medida', 'unidad medida'),
    'cantidad': ('cantidad solicitada', 'cantidad'),
    'cantidad_min': ('cantidad minima',),
    'cantidad_max': ('cantidad maxima',),
    'identificador': ('numero de procedimiento', 'numero procedimiento', 'no procedimiento', 'identificador'),
    'nombre_publicado': ('nombre publicado', 'nombre', 'nombre del procedimiento', 'descripcion del procedimiento'),
    'codigo_expediente': ('codigo expediente', 'codigo del expediente'),
    'unidad_codigo': ('codigo unidad compradora', 'codigo de la unidad compradora', 'clave uc'),
    'unidad_nombre': ('unidad compradora', 'nombre de la unidad compradora'),
    'entidad_codigo': ('codigo entidad', 'codigo inegi', 'codigo entidad federativa'),
    'estatus': ('estatus', 'estatus portal', 'estatus del procedimiento', 'estado del procedimiento'),
    'tipo_codigo': ('tipo de contratacion', 'tipo contratacion'),
    'fecha_junta_aclaraciones': ('fecha de junta de aclaraciones', 'fecha junta aclaraciones', 'junta de aclaraciones'),
    'fecha_limite_preguntas': ('fecha limite preguntas', 'fecha limite de preguntas', 'limite de preguntas'),
    'fecha_entrega_muestras': ('fecha entrega muestras', 'fecha de entrega de muestras'),
    'fecha_apertura': ('fecha de apertura', 'fecha apertura', 'fecha de presentacion y apertura de proposiciones'),
    'fecha_fallo': ('fecha de fallo', 'fecha fallo', 'fecha del fallo'),
}
HEADER_MAP = {norm(alias): key for key, aliases in ALIASES.items() for alias in aliases}
DETAIL_REQUIRED = {'numero', 'partida_especifica', 'clave_cucop', 'descripcion_detallada', 'unidad_medida'}
LIST_REQUIRED = {'identificador', 'nombre_publicado', 'unidad_nombre', 'estatus', 'tipo_codigo'}
TYPE_CODES = {'adq': 'ADQ', 'adquisiciones': 'ADQ', 'adquisicion': 'ADQ',
              'servicios': 'SER', 'servicio': 'SER', 'ser': 'SER',
              'obra publica': 'OBR', 'obras publicas': 'OBR', 'obr': 'OBR',
              'arrendamiento': 'ARR', 'arrendamientos': 'ARR', 'arr': 'ARR'}


def identifier_parts(identifier):
    match = IDENTIFIER.fullmatch(str(identifier or '').strip())
    if not match:
        raise ImportValidationError('Identificador de procedimiento inválido: %s' % identifier)
    parts = match.group(1).upper().split('-')
    return dict(tipo_procedimiento=parts[0], caracter=parts[-3], consecutivo=parts[-2],
                ejercicio=parts[-1], ordenamiento_legal='LOPSRM' if parts[0] in ('LO', 'IO') else 'LAASSP')


def business_key(row):
    # JSON preserves boundaries: no collisions from a literal separator in a description.
    triple = [row.get(k) or '' for k in ('partida_especifica', 'clave_cucop', 'descripcion_detallada')]
    return hashlib.md5(json.dumps(triple, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def diff_rows(incoming, current, previous_keys=(), key='identificador'):
    """Compare data without touching internal decisions. Gone = previous snapshot only."""
    result = {k: [] for k in ('nuevos', 'cambios', 'sin_cambios', 'gone')}
    seen = set()
    for row in incoming:
        identity = row[key]
        if identity in seen:
            raise ImportValidationError('Clave de negocio duplicada: %s' % identity)
        seen.add(identity)
        old = current.get(identity)
        if old is None:
            result['nuevos'].append({'key': identity, 'values': row})
            continue
        delta = {k: {'antes': old.get(k), 'despues': v} for k, v in row.items() if old.get(k) != v}
        entry = {'key': identity, 'values': row, 'diff': delta}
        result['cambios' if delta else 'sin_cambios'].append(entry)
    result['gone'] = [{'key': k, 'values': current[k]} for k in sorted(set(previous_keys) - seen) if k in current]
    return result


def code(value):
    if isinstance(value, bool):
        raise ImportValidationError('Un código no puede ser booleano.')
    if isinstance(value, (float, int)):
        if not math.isfinite(value) or int(value) != value:
            raise ImportValidationError('Código numérico no entero: %s' % value)
        return str(int(value))
    return str(value if value is not None else '').strip()


def number(value, required=False):
    if value is None or value == '':
        if required:
            raise ImportValidationError('Falta una cantidad obligatoria o una fórmula no tiene valor calculado.')
        return 0.0
    try:
        if isinstance(value, bool):
            raise ValueError()
        parsed = float(str(value).replace(',', '').strip())
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError()
        return parsed
    except (TypeError, ValueError) as exc:
        raise ImportValidationError('Cantidad inválida: %s' % value) from exc


def portal_datetime(value, tz_name):
    if value is None or value == '':
        return False
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        parsed = None
        for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                parsed = datetime.strptime(str(value).strip(), fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ImportValidationError('Fecha inválida: %s. Use dd/mm/yyyy HH:MM.' % value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(tz_name))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')


class WorkbookReader:
    MAX_BYTES = 25 * 1024 * 1024
    MAX_UNCOMPRESSED = 150 * 1024 * 1024
    MAX_ROWS = 50000

    def __init__(self, binary_data, filename, tz_name='America/Mexico_City'):
        self.filename = filename
        self.tz_name = tz_name
        try:
            ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ImportValidationError('Zona horaria inválida.') from exc
        if not filename.lower().endswith('.xlsx') or len(binary_data) > self.MAX_BYTES:
            raise ImportValidationError('Seleccione un archivo .xlsx de hasta 25 MB.')
        try:
            with zipfile.ZipFile(io.BytesIO(binary_data)) as archive:
                if sum(z.file_size for z in archive.infolist()) > self.MAX_UNCOMPRESSED:
                    raise ImportValidationError('El Excel supera el tamaño descomprimido permitido.')
            self.wb = openpyxl.load_workbook(io.BytesIO(binary_data), read_only=True, data_only=True)
        except (zipfile.BadZipFile, OSError, KeyError, ValueError) as exc:
            raise ImportValidationError('El archivo no es un Excel válido: %s' % exc) from exc
        self.ws = self.wb.worksheets[0]
        self.headers = []
        self.header_row = None
        self.tipo = None
        for idx, row in enumerate(self.ws.iter_rows(max_row=5, values_only=True), 1):
            headers = [HEADER_MAP.get(norm(v)) for v in row]
            names = set(headers) - {None}
            if DETAIL_REQUIRED <= names:
                self.tipo = 'detalle'
            elif LIST_REQUIRED <= names:
                self.tipo = 'listado'
            else:
                continue
            if len(names) != len([h for h in headers if h]):
                self.close()
                raise ImportValidationError('Hay encabezados duplicados o equivalentes en el archivo.')
            self.headers, self.header_row = headers, idx
            break
        if not self.tipo:
            self.close()
            raise ImportValidationError('No se detectó un encabezado válido en las primeras 5 filas.')
        if self.tipo == 'detalle' and not ('cantidad' in self.headers or {'cantidad_min', 'cantidad_max'} <= set(self.headers)):
            self.close()
            raise ImportValidationError('Se requiere Cantidad solicitada o Cantidad mínima y Cantidad máxima.')

    def close(self):
        self.wb.close()

    def detect_identifier_from_filename(self):
        match = IDENTIFIER.search(self.filename)
        return match.group(1).upper() if match else None

    def rows(self):
        result = []
        seen = {}
        for idx, row in enumerate(self.ws.iter_rows(min_row=self.header_row + 1, values_only=True), self.header_row + 1):
            if idx - self.header_row > self.MAX_ROWS:
                raise ImportValidationError('Máximo 50,000 renglones por archivo.')
            if all(v is None or v == '' for v in row):
                continue
            values = {k: v for k, v in zip(self.headers, row) if k}
            try:
                parsed = self._partida(values) if self.tipo == 'detalle' else self._procedimiento(values)
                key = business_key(parsed) if self.tipo == 'detalle' else parsed['identificador']
                if key in seen:
                    if seen[key] != parsed:
                        raise ImportValidationError('La misma clave de negocio tiene datos contradictorios.')
                    continue
                seen[key] = parsed
                result.append(parsed)
            except ImportValidationError as exc:
                raise ImportValidationError('Fila %s: %s' % (idx, exc)) from exc
        if not result:
            raise ImportValidationError('El archivo no contiene registros. No se marcarán ausencias con un archivo vacío.')
        return result

    def _partida(self, data):
        n = number(data.get('numero'), required=True)
        if n != int(n) or n <= 0:
            raise ImportValidationError('Núm. debe ser un entero positivo.')
        row = {k: code(data.get(k)) for k in PARTIDA_FIELDS if k not in ('numero', 'cantidad', 'cantidad_min', 'cantidad_max')}
        # Deliberately do not strip descriptions: exact business key, including line breaks.
        for k in ('descripcion_cucop', 'descripcion_detallada'):
            row[k] = str(data[k]) if data.get(k) is not None else ''
        if any(not row[k].strip() for k in ('partida_especifica', 'clave_cucop', 'descripcion_detallada', 'unidad_medida')):
            raise ImportValidationError('Complete partida, clave CUCoP+, descripción y unidad de medida.')
        row.update(numero=int(n), cantidad_min=number(data.get('cantidad_min')), cantidad_max=number(data.get('cantidad_max')))
        if 'cantidad_max' in self.headers and row['cantidad_min'] > row['cantidad_max']:
            raise ImportValidationError('Cantidad mínima mayor que la máxima.')
        row['cantidad'] = number(data.get('cantidad') if data.get('cantidad') not in (None, '') else data.get('cantidad_max'), required=True)
        return row

    def _procedimiento(self, data):
        identifier = code(data.get('identificador')).upper()
        identifier_parts(identifier)
        row = {k: code(data.get(k)) for k in PORTAL_FIELDS if k not in DATE_FIELDS}
        row['identificador'] = identifier
        row['unidad_codigo'] = row['unidad_codigo'] or identifier.split('-')[3]
        row['tipo_codigo'] = TYPE_CODES.get(norm(data.get('tipo_codigo')))
        if not row['tipo_codigo']:
            raise ImportValidationError('Tipo de contratación no reconocido: %s' % data.get('tipo_codigo'))
        for k in ('nombre_publicado', 'unidad_nombre', 'estatus'):
            if not row[k]:
                raise ImportValidationError('Falta %s.' % k)
        if row['entidad_codigo']:
            row['entidad_codigo'] = row['entidad_codigo'].zfill(2)
            if row['entidad_codigo'] not in {str(n).zfill(2) for n in range(1, 33)}:
                raise ImportValidationError('Código INEGI fuera de 01–32.')
        for optional in ('entidad_codigo', 'codigo_expediente'):
            if optional not in self.headers:
                row.pop(optional)
        # Only present columns may update dates; omitted headers do not erase dates.
        row.update({k: portal_datetime(data.get(k), self.tz_name) for k in DATE_FIELDS if k in self.headers})
        return row
