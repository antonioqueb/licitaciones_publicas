"""Odoo adapter: preview is read-only; commit uses a strictly filtered portal payload."""
import base64
import hashlib

from odoo import fields
from odoo.exceptions import AccessError, UserError

from ..parser import (WorkbookReader, ImportValidationError, PARTIDA_FIELDS, DATE_FIELDS,
                      business_key, diff_rows, digest, norm)
from .common import IMPORT_TOKEN, FLOW_TOKEN, require_companies


class LicitacionImporter:
    def __init__(self, env, binary_data, filename, tz_name='America/Mexico_City'):
        self.env = env
        try:
            reader = WorkbookReader(binary_data, filename, tz_name)
            try:
                self.tipo = reader.tipo
                self.identifier = reader.detect_identifier_from_filename()
                self.rows = reader.rows()
            finally:
                reader.close()
        except ImportValidationError as exc:
            raise UserError(str(exc)) from exc

    @classmethod
    def for_carga(cls, carga):
        return cls(carga.env, base64.b64decode(carga.with_context(bin_size=False).archivo), carga.archivo_nombre, carga.zona_horaria)

    def _previous(self, carga):
        return self.env['licitacion.carga'].search([
            ('scope_key', '=', carga.scope_key), ('state', '=', 'confirmada'),
            ('id', '!=', carga.id)], order='fecha_snapshot desc, id desc', limit=1)

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
                row = {'identificador': key, 'nombre_publicado': rec.nombre_publicado,
                    'codigo_expediente': rec.codigo_expediente or '',
                    'unidad_codigo': rec.unidad_compradora_id.code,
                    'unidad_nombre': norm(rec.unidad_compradora_id.name),
                    'entidad_codigo': rec.entidad_id.code or '',
                    'estatus': norm(rec.estatus_portal_id.name), 'tipo_codigo': rec.tipo_contratacion_id.code}
                row.update({k: fields.Datetime.to_string(rec[k]) if rec[k] else False for k in DATE_FIELDS})
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
        if self.tipo == 'detalle' and not carga.procedimiento_id:
            raise UserError('Asigne el detalle a un procedimiento existente.')
        previous = self._previous(carga)
        if previous and carga.fecha_snapshot < previous.fecha_snapshot:
            raise UserError('El snapshot es anterior al último confirmado de este alcance. No puede sobrescribir datos más recientes.')
        records, current, versions = self._current(carga)
        incoming = []
        for data in self.rows:
            row = dict(data, sigue_apareciendo=True)
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
        fingerprint = digest({'diff': diff, 'versions': {k: v for k, v in versions.items() if k in touched},
                              'previous_id': previous.id, 'scope': carga.scope_key, 'snapshot': carga.fecha_snapshot,
                              'assignment_note': carga.nota_asignacion, 'procedure': carga.procedimiento_id.id,
                              'congruencia': self._congruencia(carga)})
        return {'diff': diff, 'fingerprint': fingerprint, 'present_keys': keys,
                'previous_id': previous.id, 'congruencia': self._congruencia(carga)}

    def _congruencia(self, carga):
        issues = []
        if self.tipo == 'listado':
            for row in self.rows:
                if not row.get('entidad_codigo'):
                    continue
                unit = self.env['licitacion.unidad.compradora'].search([('code', '=', row['unidad_codigo'])], limit=1)
                if unit.entidad_id and unit.entidad_id.code != row['entidad_codigo']:
                    entity = self.env['licitacion.entidad.federativa'].search([('code', '=', row['entidad_codigo'])], limit=1)
                    issues.append({'target_identificador': row['identificador'], 'campo': 'entidad_id',
                        'valor_esperado': unit.entidad_id.name, 'valor_encontrado': entity.name,
                        'antes_json': unit.entidad_id.id, 'despues_json': entity.id, 'severidad': 'bloqueante'})
            return issues
        procedure = carga.procedimiento_id
        if procedure.tipo_contratacion_id.code == 'SER' and sum(norm(r['unidad_medida']) in ('pieza', 'par', 'caja') for r in self.rows) > 1:
            adq = self.env.ref('licitaciones_publicas.tipo_adq')
            issues.append({'campo': 'tipo_contratacion_id', 'valor_esperado': procedure.tipo_contratacion_id.name,
                           'valor_encontrado': 'Múltiples partidas con unidades de bienes',
                           'antes_json': procedure.tipo_contratacion_id.id, 'despues_json': adq.id,
                           'severidad': 'bloqueante'})
        if self.identifier and self.identifier != procedure.identificador:
            issues.append({'campo': 'asignacion_archivo', 'valor_esperado': procedure.identificador,
                           'valor_encontrado': self.identifier, 'antes_json': False, 'despues_json': False,
                           'severidad': 'bloqueante'})
        return issues

    def _catalog(self, model, domain, values):
        # Narrow privilege: only whitelisted catalog creation during a confirmed import.
        allowed = {'licitacion.unidad.compradora', 'licitacion.estatus.portal'}
        if model not in allowed:
            raise AccessError('Catálogo no autorizado para alta automática.')
        catalog = self.env[model].sudo().with_context(active_test=False)
        record = catalog.search(domain, limit=1)
        if not record:
            record = catalog.create(values)
            if model == 'licitacion.estatus.portal':
                manager = self.env.ref('licitaciones_publicas.group_licitaciones_manager').sudo().user_ids.filtered('active')[:1]
                manager = manager or self.env.ref('base.user_admin')
                record.activity_schedule('mail.mail_activity_data_todo', user_id=manager.id,
                                         summary='Validar nuevo estatus del portal')
        if not record.active:
            raise UserError('El catálogo %s está archivado; un administrador debe revisarlo.' % record.display_name)
        return record

    def _procedure_values(self, row):
        entity = self.env['licitacion.entidad.federativa'].search([('code', '=', row.get('entidad_codigo'))], limit=1) if row.get('entidad_codigo') else False
        unit = self._catalog('licitacion.unidad.compradora', [('code', '=', row['unidad_codigo'])],
            {'code': row['unidad_codigo'], 'name': row['unidad_nombre'], 'entidad_id': entity.id if entity else False})
        status = self._catalog('licitacion.estatus.portal', [('code', '=', norm(row['estatus']).upper().replace(' ', '_'))],
            {'code': norm(row['estatus']).upper().replace(' ', '_'), 'name': row['estatus'], 'tipo': 'auto_creado', 'estado': 'por_revisar'})
        tipo = self.env['licitacion.tipo.contratacion'].search([('code', '=', row['tipo_codigo'])], limit=1)
        if not tipo:
            raise UserError('No existe el tipo de contratación %s.' % row['tipo_codigo'])
        if norm(unit.name) != norm(row['unidad_nombre']):
            unit.write({'name': row['unidad_nombre']})
        if entity and not unit.entidad_id:
            unit.write({'entidad_id': entity.id})
        vals = {'identificador': row['identificador'], 'nombre_publicado': row['nombre_publicado'],
                'unidad_compradora_id': unit.id, 'estatus_portal_id': status.id, 'tipo_contratacion_id': tipo.id}
        if 'codigo_expediente' in row:
            vals['codigo_expediente'] = row['codigo_expediente'] or False
        vals.update({k: row[k] for k in DATE_FIELDS if k in row})
        return vals

    def commit(self, prepared, carga):
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
                    elif category == 'cambios':
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
                    self._snapshot(env, carga, rec, row, True)
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
            procedure = procedure_model.search([('identificador', '=', identifier)], limit=1) if identifier else carga.procedimiento_id
            existing = env['licitacion.incidencia'].search([
                ('procedimiento_id', '=', procedure.id), ('campo', '=', issue['campo']),
                ('state', '=', 'abierta')], limit=1)
            if not existing:
                env['licitacion.incidencia'].create(dict(issue, carga_id=carga.id,
                    procedimiento_id=procedure.id, origen='procedimiento'))

    def _snapshot(self, env, carga, procedure, payload, present):
        env['licitacion.aparicion'].create({'carga_id': carga.id, 'procedimiento_id': procedure.id,
            'presente': present, 'datos_snapshot': payload, 'nombre_publicado_snapshot': procedure.nombre_publicado,
            'estatus_portal_id_snapshot': procedure.estatus_portal_id.id,
            'unidad_compradora_id_snapshot': procedure.unidad_compradora_id.id,
            'fecha_junta_snapshot': procedure.fecha_junta_aclaraciones,
            'fecha_apertura_snapshot': procedure.fecha_apertura, 'fecha_fallo_snapshot': procedure.fecha_fallo})
