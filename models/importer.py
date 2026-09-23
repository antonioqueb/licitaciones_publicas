"""Odoo adapter: preview is read-only; commit uses a strictly filtered portal payload."""
import base64
import hashlib
import json

from psycopg2.errors import SerializationFailure, UniqueViolation

from odoo import fields
from odoo.exceptions import AccessError, UserError

from ..parser import (WorkbookReader, ImportValidationError, PARTIDA_FIELDS, DATE_FIELDS, LIST_METADATA_FIELDS,
                      business_key, diff_rows, digest, norm, identifier_parts)
from .common import IMPORT_TOKEN, FLOW_TOKEN, require_companies
from ..catalog_resolution import CATALOGS, catalog_norm, choose_record


class LicitacionImporter:
    def __init__(self, env, binary_data, filename, tz_name='America/Mexico_City'):
        self.env = env
        self.filename = filename
        self._records_cache = {}
        profiles = env['licitacion.tipo.archivo'].search([('activo', '=', True)])
        self.profiles = [rec._configuration() for rec in profiles]
        try:
            reader = WorkbookReader(binary_data, filename, tz_name, profiles=self.profiles)
            try:
                self.tipo = reader.tipo
                self.subtipo = reader.subtipo
                self.config = reader.config
                self.tipo_archivo_id = reader.config['id']
                self.identifier = reader.detect_identifier_from_filename()
                self.rows = reader.rows()
                self.content_identifiers = reader.identificadores_contenido
                if not self.identifier and len(self.content_identifiers) == 1:
                    self.identifier = next(iter(self.content_identifiers))
            finally:
                reader.close()
        except ImportValidationError as exc:
            raise UserError(str(exc)) from exc

    def resolve_catalog_value(self, campo, texto, procedimiento=None):
        """Read-only for preview. Missing references are materialized at commit."""
        model, _fk, groups = CATALOGS[campo]
        domain = [('activo', '=', True)] if campo == 'tipo_procedimiento' else []
        if campo == 'estatus_portal':
            domain = [('estado', '!=', 'inactivo')]
        if campo not in self._records_cache:
            self._records_cache[campo] = self.env[model].search(domain)
        records = self._records_cache[campo]
        if campo == 'entidad_federativa' and str(texto or '').strip().isdigit():
            return records.filtered(lambda r: r.code == str(texto).strip().zfill(2))[:1]
        return choose_record(records, groups, texto)[0]

    def _catalog_texts(self, row):
        parts = identifier_parts(row['identificador'])
        return {'entidad_federativa': row.get('entidad_nombre') or row.get('entidad_codigo', ''),
                'estatus_portal': row.get('estatus', ''), 'tipo_contratacion': row.get('tipo_codigo', ''),
                'tipo_procedimiento': parts['tipo_procedimiento'], 'caracter_procedimiento': parts['caracter'],
                'unidad_compradora': row.get('unidad_codigo', '')}

    def _row_catalogs(self, row):
        return {key: self.resolve_catalog_value(key, value) for key, value in self._catalog_texts(row).items()}

    def _list_comparison(self, row):
        resolved = self._row_catalogs(row)
        result = {key: value for key, value in row.items() if key not in ('_fila', 'entidad_nombre')}
        result.update(unidad_codigo=resolved['unidad_compradora'].code or row.get('unidad_codigo', ''),
                      unidad_nombre=norm(row.get('unidad_nombre')),
                      entidad_codigo=resolved['entidad_federativa'].code or self._catalog_texts(row)['entidad_federativa'],
                      estatus=norm(resolved['estatus_portal'].name or row.get('estatus')),
                      tipo_codigo=resolved['tipo_contratacion'].code or row.get('tipo_codigo', ''))
        return result

    @classmethod
    def for_carga(cls, carga):
        return cls(carga.env, base64.b64decode(carga.with_context(bin_size=False).archivo), carga.archivo_nombre, carga.zona_horaria)

    def _previous(self, carga):
        return self.env['licitacion.carga'].search([
            ('scope_key', '=', carga.scope_key), ('state', '=', 'confirmada'),
            ('id', '!=', carga.id)], order='fecha_snapshot desc, id desc', limit=1)

    def _baseline_warning(self, previous):
        return (False if previous else
                'No existe una carga confirmada anterior para este tipo y alcance. '
                'Se compara contra los registros actuales del sistema; las ausencias no se marcarán.')

    def _validate_previous_records(self, previous, current):
        if not previous:
            return
        if self.tipo == 'listado':
            expected = set(previous.aparicion_ids.filtered('presente').procedimiento_id.mapped('identificador'))
        else:
            expected = {business_key(row) for snapshot in previous.aparicion_ids
                        for row in (snapshot.datos_snapshot or {}).get('partidas', [])}
        if expected - current.keys():
            raise UserError('La carga confirmada de referencia contiene registros que no están disponibles. '
                            'Revise las empresas activas y los datos antes de continuar; no se usará una comparación vacía.')

    def _current(self, carga):
        model = 'licitacion.procedimiento' if self.tipo == 'listado' else 'licitacion.partida'
        # All records visible in this scope, including archived ones, preserve identity.
        records = self.env[model].with_context(active_test=False).search(
            [] if self.tipo == 'listado' else [('procedimiento_id', '=', carga.procedimiento_id.id)])
        current, versions = {}, {}
        for rec in records:
            if self.tipo == 'detalle':
                row = {k: (rec[k] or '') if rec._fields[k].type in ('char', 'text') else rec[k] for k in PARTIDA_FIELDS}
                key = rec.clave_hash
                row['clave_hash'] = key
            else:
                key = rec.identificador
                raw = rec.catalogos_portal or {}
                row = {'identificador': key, 'nombre_publicado': rec.nombre_publicado,
                    'codigo_expediente': rec.codigo_expediente or '',
                    'unidad_codigo': rec.unidad_compradora_id.code or raw.get('unidad_compradora', ''),
                    'unidad_nombre': norm(raw.get('unidad_nombre') or rec.unidad_compradora_id.name),
                    'entidad_codigo': rec.entidad_id.code or raw.get('entidad_federativa', ''),
                    'estatus': norm(rec.estatus_portal_id.name or raw.get('estatus_portal', '')),
                    'tipo_codigo': rec.tipo_contratacion_id.code or raw.get('tipo_contratacion', '')}
                for crossing, column in [('entidad_federativa', 'entidad_codigo'), ('tipo_contratacion', 'tipo_codigo'), ('unidad_compradora', 'unidad_codigo')]:
                    if crossing in raw and not self.resolve_catalog_value(crossing, raw[crossing]):
                        row[column] = raw[crossing]
                row.update({k: fields.Datetime.to_string(rec[k]) if rec[k] else False for k in DATE_FIELDS})
                row.update({k: rec[k] if k == 'numero_listado' else rec[k] or '' for k in LIST_METADATA_FIELDS})
            row['sigue_apareciendo'] = rec.sigue_apareciendo
            current[key] = row
            versions[key] = {'id': rec.id, 'write_date': fields.Datetime.to_string(rec.write_date)}
        return records, current, versions

    def compute_diff(self, carga):
        carga.ensure_one()
        require_companies(carga, carga.company_ids)
        if set(carga.company_ids.ids) != set(self.env.companies.ids):
            raise UserError('Active exactamente las empresas usadas al preparar esta carga.')
        if self.tipo != carga.tipo_detectado:
            raise UserError('El archivo no coincide con el tipo detectado.')
        if self.tipo == 'catalogo':
            return self._catalog_diff(carga)
        if self.tipo == 'detalle' and not carga.procedimiento_id:
            raise UserError('Asigne el detalle a un procedimiento existente.')
        previous = self._previous(carga)
        if previous and carga.fecha_snapshot < previous.fecha_snapshot:
            raise UserError('El snapshot es anterior al último confirmado de este alcance. No puede sobrescribir datos más recientes.')
        records, current, versions = self._current(carga)
        self._validate_previous_records(previous, current)
        incoming = []
        for data in self.rows:
            row = dict(self._list_comparison(data) if self.tipo == 'listado' else data, sigue_apareciendo=True)
            if self.tipo == 'detalle':
                row['clave_hash'] = business_key(data)
            else:
                row['estatus'] = norm(row['estatus'])
                row['unidad_nombre'] = norm(row['unidad_nombre'])
            incoming.append(row)
        key = 'identificador' if self.tipo == 'listado' else 'clave_hash'
        keys = [row[key] for row in incoming]
        if self.tipo == 'listado':
            if records.filtered(lambda r: r.identificador in keys and r.ultimo_snapshot_id and r.ultimo_snapshot_id.fecha_snapshot > carga.fecha_snapshot):
                raise UserError('Un procedimiento tiene un snapshot más reciente de otro alcance. No se sobrescribirá.')
        elif self.env['licitacion.carga'].search_count([
            ('procedimiento_id', '=', carga.procedimiento_id.id), ('tipo_detectado', '=', 'detalle'),
            ('state', '=', 'confirmada'), ('fecha_snapshot', '>', carga.fecha_snapshot)]):
            raise UserError('El procedimiento ya tiene un detalle más reciente de otro alcance.')
        # The global identifier is unique even when company rules hide a procedure.
        if self.tipo == 'listado':
            hidden = self.env['licitacion.procedimiento'].sudo().with_context(active_test=False).search_count([
                ('identificador', 'in', keys), ('id', 'not in', records.ids)])
            if hidden:
                raise AccessError('El archivo incluye procedimientos de empresas no activas o no autorizadas. Revise el alcance y las empresas.')
        previous_keys = previous.present_keys or []
        try:
            diff = diff_rows(incoming, current, previous_keys, key=key)
        except ImportValidationError as exc:
            raise UserError(str(exc)) from exc
        for category, entries in diff.items():
            for entry in entries:
                entry['record_id'] = versions.get(entry['key'], {}).get('id', False)
        touched = set(keys) | set(previous_keys)
        congruencia = self._congruencia(carga)
        fingerprint = digest({'diff': diff, 'versions': {k: v for k, v in versions.items() if k in touched},
                              'previous_id': previous.id, 'scope': carga.scope_key, 'snapshot': carga.fecha_snapshot,
                              'assignment_note': carga.nota_asignacion, 'procedure': carga.procedimiento_id.id,
                              'congruencia': congruencia, 'configuration': self.profiles,
                              'catalogs': self._catalog_state()})
        return {'diff': diff, 'fingerprint': fingerprint, 'present_keys': keys,
                'previous_id': previous.id, 'aviso_base': self._baseline_warning(previous), 'congruencia': congruencia}

    def _catalog_state(self):
        return {
            'crossings': {key: self.env[model].with_context(active_test=False).search([]).read(
                list(dict.fromkeys(['id', 'write_date', *[field for group in groups for field in group],
                    *[field for field in ('active', 'activo', 'estado', 'nombres_alternativos') if field in self.env[model]._fields]])))
                for key, (model, _fk, groups) in CATALOGS.items()},
            'prefijos': [(r.prefijo, r.activo) for r in self.env['licitacion.tipo.procedimiento'].search([])],
            'caracteres': self.env['licitacion.caracter.procedimiento'].search([]).mapped('clave'),
            'sai': [(r.code, r.active, sorted(r.cucop_ids.filtered('active').mapped('code')))
                    for r in self.env['licitacion.clave.sai'].with_context(active_test=False).search([
                        ('code', 'in', list({row.get('partida_especifica') for row in self.rows if row.get('partida_especifica')}))])],
        }

    def _identifier_issues(self, identifier, target=None):
        if not identifier:
            return []
        parts = identifier_parts(identifier)
        tests = [('tipo_procedimiento', parts['tipo_procedimiento']), ('caracter_procedimiento', parts['caracter'])]
        issues = []
        for field, value in tests:
            if not self.resolve_catalog_value(field, value):
                issues.append({'campo': field, 'target_identificador': target or identifier,
                    'identificador_observado': identifier, 'valor_esperado': 'Identificador existente en catálogo del cliente',
                    'valor_encontrado': value, 'antes_json': False, 'despues_json': value, 'severidad': 'advertencia',
                    'es_valor_no_reconocido': True, 'detalle': json.dumps({'archivo': self.filename, 'identificador': identifier}, ensure_ascii=False, indent=2)})
        return issues

    def _congruencia(self, carga):
        issues = []
        if self.tipo == 'listado':
            for row in self.rows:
                procedure = self.env['licitacion.procedimiento'].with_context(active_test=False).search([('identificador', '=', row['identificador'])], limit=1)
                for field, text in self._catalog_texts(row).items():
                    if self.resolve_catalog_value(field, text, procedure):
                        continue
                    model, fk, groups = CATALOGS[field]
                    _matched, suggestion = choose_record(self.env[model].search([]), groups, text)
                    issues.append({'target_identificador': row['identificador'], 'identificador_observado': row['identificador'],
                        'campo': field, 'valor_esperado': procedure[fk].display_name if procedure and procedure[fk] else suggestion,
                        'valor_encontrado': text, 'antes_json': procedure[fk].id if procedure else False,
                        'despues_json': False, 'severidad': 'advertencia', 'es_valor_no_reconocido': True,
                        'detalle': json.dumps({'fila': row.get('_fila'), 'archivo': carga.archivo_nombre,
                            'identificador': row['identificador'], 'unidad_publicada': row.get('unidad_nombre')}, ensure_ascii=False, indent=2)})
            return issues
        procedure = carga.procedimiento_id
        for identifier in sorted({procedure.identificador, self.identifier, *self.content_identifiers} - {None, False}):
            issues.extend(self._identifier_issues(identifier, procedure.identificador))
        sai = {r.code: r for r in self.env['licitacion.clave.sai'].search([
            ('code', 'in', list({r['partida_especifica'] for r in self.rows}))])}
        for row in self.rows:
            entry = sai.get(row['partida_especifica'])
            issue = {'target_partida_hash': business_key(row), 'antes_json': False,
                     'despues_json': row['partida_especifica'], 'valor_encontrado': row['partida_especifica']}
            if not entry:
                issues.append(dict(issue, campo='partida_sai', severidad='bloqueante',
                                   valor_esperado='Partida específica existente en catálogo SAI'))
            elif row['clave_cucop'] not in entry.cucop_ids.filtered('active').mapped('code'):
                issues.append(dict(issue, campo='cucop_sai', severidad='advertencia',
                    valor_esperado=', '.join(entry.cucop_ids.filtered('active').mapped('code')),
                    valor_encontrado=row['clave_cucop'], despues_json=row['clave_cucop']))
        if self.content_identifiers and (self.content_identifiers != {self.identifier} or self.content_identifiers != {procedure.identificador}):
            issues.append({'campo': 'asignacion_archivo', 'valor_esperado': procedure.identificador,
                'valor_encontrado': 'Nombre: %s; contenido: %s' % (self.identifier or 'Sin identificador', ', '.join(sorted(self.content_identifiers))),
                'antes_json': False, 'despues_json': False, 'severidad': 'advertencia'})
        if self.identifier and self.identifier != procedure.identificador:
            issues.append({'campo': 'asignacion_archivo', 'valor_esperado': procedure.identificador,
                           'valor_encontrado': self.identifier, 'antes_json': False, 'despues_json': False,
                           'severidad': 'advertencia'})
        return issues

    def _ensure_status(self, text):
        # Only statuses are auto-created; the unknown-value warning remains.
        if not (text or '').strip():
            return self.env['licitacion.estatus.portal']
        catalog = self.env['licitacion.estatus.portal'].sudo().with_context(active_test=False)
        code = catalog_norm(text).replace(' ', '_')
        record = catalog.search([('code', '=', code)], limit=1)
        if not record:
            try:
                with self.env.cr.savepoint():
                    record = catalog.create({'code': code, 'name': text, 'tipo': 'auto_creado', 'estado': 'por_revisar'})
            except UniqueViolation as exc:
                # A concurrent import inserted the status after our repeatable-read snapshot.
                # Let Odoo retry the complete RPC against a fresh snapshot.
                raise SerializationFailure('El catálogo de estatus cambió durante la confirmación.') from exc
        return record

    def _procedure_values(self, row):
        resolved = self._row_catalogs(row)
        if not resolved['estatus_portal']:
            resolved['estatus_portal'] = self._ensure_status(row.get('estatus'))
        vals = {'identificador': row['identificador'], 'nombre_publicado': row['nombre_publicado'],
                'catalogos_portal': dict(self._catalog_texts(row), unidad_nombre=row.get('unidad_nombre', ''))}
        # An unknown value never erases a previous valid mapping.
        vals.update({CATALOGS[key][1]: record.id for key, record in resolved.items() if record})
        if 'codigo_expediente' in row:
            vals['codigo_expediente'] = row['codigo_expediente'] or False
        vals.update({k: row[k] for k in LIST_METADATA_FIELDS if k in row})
        vals.update({k: row[k] for k in DATE_FIELDS if k in row})
        return vals

    def commit(self, prepared, carga):
        if self.tipo == 'catalogo':
            return self._commit_catalog(prepared, carga)
        env = self.env(context=dict(self.env.context, _lp_import=IMPORT_TOKEN, _lp_flow=FLOW_TOKEN))
        procedure_model = env['licitacion.procedimiento']
        model = procedure_model if self.tipo == 'listado' else env['licitacion.partida']
        diff = prepared['diff']
        # No commit()/savepoint swallowing: all changes, snapshots, and status are atomic.
        for category in ('nuevos', 'cambios', 'sin_cambios'):
            for entry in diff[category]:
                row = entry['values']
                rec = model.browse(entry['record_id']) if entry['record_id'] else model
                if self.tipo == 'listado':
                    source_row = next(r for r in self.rows if r['identificador'] == row['identificador'])
                    vals = self._procedure_values(source_row)
                    if not rec:
                        rec = model.create(dict(vals, primer_snapshot_id=carga.id))
                    else:
                        vals.pop('identificador', None)
                        if rec.fecha_fallo and vals.get('fecha_fallo') and fields.Datetime.to_datetime(vals['fecha_fallo']) > rec.fecha_fallo and not rec.fecha_fallo_original:
                            vals['fecha_fallo_original'] = rec.fecha_fallo
                        changed_dates = [k for k in DATE_FIELDS if k in entry.get('diff', {}) and vals.get(k)]
                        if rec.state == 'descartado' and changed_dates:
                            vals['reapertura_habilitada'] = True
                            rec.message_post(body='El portal actualizó fechas límite: %s. El estado interno permanece Descartado; revise una nueva criba.' % ', '.join(changed_dates))
                            rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.user_id.id, summary='Revisar fechas nuevas de procedimiento descartado')
                        rec.write(vals)
                    rec.write({'ultimo_snapshot_id': carga.id, 'sigue_apareciendo': True, 'fecha_ya_no_aparece': False})
                    self._snapshot(env, carga, rec, source_row, True)
                else:
                    vals = {k: row[k] for k in PARTIDA_FIELDS}
                    if not rec:
                        rec = model.create(dict(vals, procedimiento_id=carga.procedimiento_id.id, importada=True))
                    elif category == 'cambios':
                        # Preserve company assignments, providers, cost and screening decisions.
                        rec.write({k: vals[k] for k in entry['diff'] if k in vals})
                    if not rec.importada:
                        rec.write({'importada': True})
                    if not rec.sigue_apareciendo:
                        rec.write({'sigue_apareciendo': True, 'fecha_ya_no_aparece': False})
        for entry in diff['gone']:
            rec = model.browse(entry['record_id'])
            if self.tipo == 'listado' and rec.ultimo_snapshot_id.fecha_snapshot > carga.fecha_snapshot:
                raise UserError('No se puede marcar ausente un procedimiento con una aparición posterior en otro alcance.')
            if rec.sigue_apareciendo:
                rec.write({'sigue_apareciendo': False, 'fecha_ya_no_aparece': carga.fecha_snapshot})
            if self.tipo == 'listado':
                self._snapshot(env, carga, rec, entry['values'], False)
        if self.tipo == 'detalle':
            self._snapshot(env, carga, carga.procedimiento_id, {'partidas': self.rows, 'gone': [e['key'] for e in diff['gone']]}, True)
        for issue in prepared['congruencia']:
            issue = dict(issue)
            identifier = issue.pop('target_identificador', None)
            partida_hash = issue.pop('target_partida_hash', None)
            procedure = procedure_model.with_context(active_test=False).search([('identificador', '=', identifier)], limit=1) if identifier else carga.procedimiento_id
            partida = env['licitacion.partida'].search([('procedimiento_id', '=', procedure.id), ('clave_hash', '=', partida_hash)], limit=1) if partida_hash else env['licitacion.partida']
            existing = env['licitacion.incidencia'].search([
                ('procedimiento_id', '=', procedure.id), ('campo', '=', issue['campo']),
                ('partida_id', '=', partida.id), ('carga_id', '=', carga.id),
                ('identificador_observado', '=', issue.get('identificador_observado', False)),
                ('state', '=', 'abierta')], limit=1)
            if issue.get('es_valor_no_reconocido') and procedure:
                issue['antes_json'] = procedure[CATALOGS[issue['campo']][1]].id
            if not existing:
                env['licitacion.incidencia'].create(dict(issue, carga_id=carga.id,
                    procedimiento_id=procedure.id, partida_id=partida.id,
                    origen='partida' if partida else 'procedimiento' if procedure else 'carga'))

    def _catalog_diff(self, carga):
        if not self.env.su and not self.env.user.has_group('licitaciones_publicas.group_licitaciones_manager'):
            raise AccessError('Solo un administrador puede cargar el catálogo SAI.')
        if self.env['licitacion.carga'].sudo().search_count([
                ('tipo_detectado', '=', 'catalogo'), ('state', '=', 'confirmada'),
                ('id', '!=', carga.id), ('fecha_snapshot', '>', carga.fecha_snapshot)]):
            raise UserError('El catálogo SAI ya tiene una carga confirmada más reciente.')
        previous = self._previous(carga)
        grouped = {}
        for row in self.rows:
            entry = grouped.setdefault(row['code'], {'code': row['code'], 'name': row['name'], 'cucop': {}})
            if entry['name'] != row['name']:
                raise UserError('Una partida SAI tiene descripciones contradictorias: %s.' % row['code'])
            entry['cucop'][row['cucop_code']] = row['cucop_name']
        current = {}
        records = self.env['licitacion.clave.sai'].with_context(active_test=False).search([('code', 'in', list(grouped))])
        for rec in records:
            current[rec.code] = {'code': rec.code, 'name': rec.name,
                                'cucop': {c.code: c.name for c in rec.cucop_ids}}
        diff = diff_rows(list(grouped.values()), current, key='code')
        for entries in diff.values():
            for entry in entries:
                entry['record_id'] = records.filtered(lambda r: r.code == entry['key']).id
        return {'diff': diff, 'present_keys': list(grouped), 'congruencia': [],
                'previous_id': previous.id, 'aviso_base': self._baseline_warning(previous),
                'fingerprint': digest({'diff': diff, 'configuration': self.profiles,
                                      'previous_id': previous.id,
                                      'scope': carga.scope_key, 'snapshot': carga.fecha_snapshot,
                                      'versions': [(r.id, r.write_date, r.active, [(c.id, c.write_date, c.active) for c in r.cucop_ids]) for r in records]})}

    def _commit_catalog(self, prepared, carga):
        from odoo import Command
        if not self.env.su and not self.env.user.has_group('licitaciones_publicas.group_licitaciones_manager'):
            raise AccessError('Solo un administrador puede cargar el catálogo SAI.')
        for category in ('nuevos', 'cambios', 'sin_cambios'):
            for entry in prepared['diff'][category]:
                row = entry['values']
                cucops = self.env['licitacion.clave.cucop']
                for code, name in row['cucop'].items():
                    rec = cucops.with_context(active_test=False).search([('code', '=', code)], limit=1)
                    if not rec:
                        rec = cucops.create({'code': code, 'name': name})
                    elif not rec.active:
                        raise UserError('Reactive la clave CUCoP+ antes de importarla: %s.' % code)
                    elif rec.name != name:
                        rec.write({'name': name})
                    cucops |= rec
                model = self.env['licitacion.clave.sai']
                rec = model.browse(entry['record_id'])
                vals = {'code': row['code'], 'name': row['name'], 'cucop_ids': [Command.set(cucops.ids)]}
                if not rec:
                    model.create(vals)
                elif not rec.active:
                    raise UserError('Reactive la partida SAI antes de importarla: %s.' % row['code'])
                elif category == 'cambios':
                    rec.write(vals)

    def _snapshot(self, env, carga, procedure, payload, present):
        env['licitacion.aparicion'].create({'carga_id': carga.id, 'procedimiento_id': procedure.id,
            'presente': present, 'datos_snapshot': payload, 'nombre_publicado_snapshot': procedure.nombre_publicado,
            'estatus_portal_id_snapshot': procedure.estatus_portal_id.id,
            'unidad_compradora_id_snapshot': procedure.unidad_compradora_id.id,
            'fecha_junta_snapshot': procedure.fecha_junta_aclaraciones,
            'fecha_apertura_snapshot': procedure.fecha_apertura, 'fecha_fallo_snapshot': procedure.fecha_fallo})
