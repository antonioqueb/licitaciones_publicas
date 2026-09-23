"""Catalog identities and normalization shared by import and correction."""
import re
from difflib import get_close_matches

from unidecode import unidecode


# model, procedure FK, ordered groups of exact match fields
CATALOGS = {
    'entidad_federativa': ('licitacion.entidad.federativa', 'entidad_portal_id', (('nombre',), ('name',))),
    'estatus_portal': ('licitacion.estatus.portal', 'estatus_portal_id', (('code',), ('name',))),
    'tipo_contratacion': ('licitacion.tipo.contratacion', 'tipo_contratacion_id', (('code',), ('name',))),
    'tipo_procedimiento': ('licitacion.tipo.procedimiento', 'tipo_procedimiento_id', (('prefijo',),)),
    'caracter_procedimiento': ('licitacion.caracter.procedimiento', 'caracter_procedimiento_id', (('clave',),)),
    'unidad_compradora': ('licitacion.unidad.compradora', 'unidad_compradora_id', (('code',),)),
}


def catalog_norm(text):
    return re.sub(r'\s+', ' ', unidecode(str(text or ''))).strip().upper()


def aliases(text):
    return list(dict.fromkeys(catalog_norm(part) for part in (text or '').split(',') if catalog_norm(part)))


def choose_record(records, groups, text):
    """Exact fields first, then whole aliases. Ambiguity never picks arbitrarily."""
    key = catalog_norm(text)
    if not key:
        return records[:0], ''
    for group in groups:
        matches = records.filtered(lambda rec: any(catalog_norm(rec[field]) == key for field in group))
        if matches:
            return (matches if len(matches) == 1 else records[:0]), ''
    if 'nombres_alternativos' in records._fields:
        matches = records.filtered(lambda rec: key in aliases(rec.nombres_alternativos))
        if matches:
            return (matches if len(matches) == 1 else records[:0]), ''
    names = {catalog_norm(rec.display_name): rec.display_name for rec in records}
    similar = get_close_matches(key, list(names), n=1, cutoff=0.65)
    return records[:0], names[similar[0]] if similar else ''
