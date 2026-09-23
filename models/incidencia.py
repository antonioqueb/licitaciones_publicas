from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..parser import DATE_FIELDS, identifier_parts
from ..catalog_resolution import CATALOGS, aliases
from .common import IMPORT_TOKEN, FLOW_TOKEN, imported, internal, lock, modal

RESOLVABLE = {'procedimiento': {'tipo_contratacion_id', 'unidad_compradora_id', 'entidad_id', 'nombre_publicado', *DATE_FIELDS},
              'partida': {'cantidad', 'cantidad_min', 'cantidad_max', 'unidad_medida', 'descripcion_cucop'}}


class Incidencia(models.Model):
    _name = 'licitacion.incidencia'
    _description = 'Incidencia de congruencia del portal'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'licitacion.retained']
    _order = 'severidad desc, create_date desc'
    _rec_name = 'campo'

    carga_id = fields.Many2one('licitacion.carga', string='Carga', ondelete='restrict')
    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', ondelete='restrict')
    identificador_observado = fields.Char(string='Identificador observado', readonly=True)
    partida_id = fields.Many2one('licitacion.partida', string='Partida', ondelete='restrict')
    origen = fields.Selection([('procedimiento', 'Procedimiento'), ('partida', 'Partida'), ('carga', 'Fila pendiente de catálogo')], string='Origen', required=True)
    campo = fields.Char(string='Campo', required=True)
    valor_esperado = fields.Text(string='Valor actual')
    valor_encontrado = fields.Text(string='Valor encontrado')
    detalle = fields.Text(string='Contexto del archivo', readonly=True)
    es_valor_no_reconocido = fields.Boolean(string='Valor de catálogo no reconocido', readonly=True)
    antes_json = fields.Json(readonly=True)
    despues_json = fields.Json(readonly=True)
    severidad = fields.Selection([('bloqueante', 'Bloqueante'), ('advertencia', 'Advertencia')], string='Severidad', required=True, tracking=True)
    state = fields.Selection([('abierta', 'Abierta'), ('resuelta', 'Resuelta'), ('ignorada', 'Ignorada')], string='Estado', default='abierta', required=True, tracking=True)
    nota_resolucion = fields.Text(string='Nota de resolución', readonly=True)
    resuelta_por_id = fields.Many2one('res.users', string='Resuelta por', readonly=True)
    fecha_resolucion = fields.Datetime(string='Fecha de resolución', readonly=True)
    escalada_fecha = fields.Datetime(string='Escalada el', readonly=True)

    @api.constrains('es_valor_no_reconocido', 'severidad', 'campo', 'state', 'nota_resolucion', 'procedimiento_id')
    def _check_correction(self):
        for rec in self:
            if rec.es_valor_no_reconocido and (rec.severidad != 'advertencia' or rec.campo not in CATALOGS):
                raise ValidationError('Un valor de catálogo no reconocido siempre es una advertencia.')
            if rec.es_valor_no_reconocido and not rec.procedimiento_id:
                raise ValidationError('La corrección de catálogo debe conservar el procedimiento afectado.')
            if rec.state in ('resuelta', 'ignorada') and not (rec.nota_resolucion or '').strip():
                raise ValidationError('Resolver o ignorar requiere una nota.')

    @api.constrains('partida_id', 'procedimiento_id', 'origen', 'carga_id')
    def _check_target(self):
        for rec in self:
            if rec.origen == 'carga' and (not rec.carga_id or not rec.identificador_observado):
                raise ValidationError('Una fila pendiente requiere carga e identificador observado.')
            if rec.origen != 'carga' and not rec.procedimiento_id:
                raise ValidationError('Esta incidencia requiere un procedimiento.')
            if rec.origen == 'partida' and not rec.partida_id:
                raise ValidationError('Una incidencia de partida requiere el renglón afectado.')
            if rec.partida_id and rec.partida_id.procedimiento_id != rec.procedimiento_id:
                raise ValidationError('La partida pertenece a otro procedimiento.')

    @api.model_create_multi
    def create(self, vals_list):
        if not imported(self.env):
            raise AccessError('Las incidencias se generan durante la importación.')
        records = super().create(vals_list)
        for rec in records:
            responsible = rec.procedimiento_id.user_id or rec.carga_id.user_id
            summary = 'Revisar incidencia de importación'
            if rec.es_valor_no_reconocido:
                managers = self.env.ref('licitaciones_publicas.group_licitaciones_manager').sudo().all_user_ids
                scope = rec.carga_id.company_ids or rec.procedimiento_id.company_ids
                responsible = managers.filtered(lambda u: u.active and (not scope or bool(u.company_ids & scope)))[:1] or self.env.ref('base.user_admin')
                summary = "%s no reconocido: '%s'" % (rec.campo, rec.valor_encontrado or '(vacío)')
            rec.activity_schedule('mail.mail_activity_data_todo', user_id=responsible.id, summary=summary[:200])
        return records

    def write(self, vals):
        if not internal(self.env):
            raise AccessError('Utilice Resolver o Ignorar e indique una nota.')
        if set(vals) - {'state', 'nota_resolucion', 'resuelta_por_id', 'fecha_resolucion', 'escalada_fecha'}:
            raise AccessError('La evidencia original de la incidencia es inmutable.')
        return super().write(vals)

    def action_resolver(self):
        self.ensure_one()
        return modal(self.env['licitacion.resolver.incidencia.wizard'], {'incidencia_id': self.id, 'decision': 'resolver'})

    def action_ignorar(self):
        self.ensure_one()
        return modal(self.env['licitacion.resolver.incidencia.wizard'], {'incidencia_id': self.id, 'decision': 'ignorar'})

    def _resolve(self, decision, nota, catalog_record=None, guardar_alias=False):
        self.ensure_one()
        self.check_access('write')
        if self.es_valor_no_reconocido and not self.env.su and not self.env.user.has_group('licitaciones_publicas.group_licitaciones_manager'):
            raise AccessError('Solo un administrador de Licitaciones puede atender correcciones de catálogo.')
        lock(self)
        if not (nota or '').strip() or self.state != 'abierta':
            raise ValidationError('Una incidencia abierta requiere una nota de resolución.')
        if decision not in ('resolver', 'ignorar'):
            raise ValidationError('Decisión desconocida.')
        if decision == 'resolver':
            if self.es_valor_no_reconocido:
                self._apply_catalog(catalog_record, guardar_alias)
            elif self.campo in ('prefijo_identificador', 'caracter_identificador'):
                parts = identifier_parts(self.identificador_observado)
                if self.campo == 'prefijo_identificador':
                    valid = self.env['licitacion.tipo.procedimiento'].search_count([('prefijo', '=', parts['tipo_procedimiento']), ('activo', '=', True)])
                else:
                    valid = self.env['licitacion.caracter.procedimiento'].search_count([('clave', '=', parts['caracter'])])
                if not valid:
                    raise UserError('Registre primero el identificador en el catálogo del cliente. Después vuelva a cargar las filas pendientes.')
            elif self.campo in ('partida_sai', 'cucop_sai'):
                sai = self.env['licitacion.clave.sai'].search([('code', '=', self.partida_id.partida_especifica)], limit=1)
                if not sai or (self.campo == 'cucop_sai' and self.partida_id.clave_cucop not in sai.cucop_ids.filtered('active').mapped('code')):
                    raise UserError('Corrija primero el catálogo SAI y su relación con CUCoP+.')
            elif self.campo == 'asignacion_archivo':
                # La nota obligatoria documenta también diferencias detectadas
                # en el contenido de un archivo asociado automáticamente.
                # La carga cerrada y su procedimiento permanecen inmutables.
                pass
            else:
                if self.campo not in RESOLVABLE.get(self.origen, set()):
                    raise UserError('Este campo no admite resolución automática.')
                target = self.partida_id if self.origen == 'partida' else self.procedimiento_id
                if self.campo == 'entidad_id':
                    target = self.procedimiento_id.unidad_compradora_id
                lock(target)
                field = target._fields[self.campo]
                current = target[self.campo]
                if field.type == 'many2one':
                    current = current.id
                    self.env[field.comodel_name].browse(self.despues_json).check_access('read')
                elif field.type == 'datetime':
                    current = fields.Datetime.to_string(current) if current else False
                if current != self.antes_json:
                    raise UserError('El campo cambió desde que se generó la incidencia. Revise una nueva carga.')
                target.with_context(_lp_import=IMPORT_TOKEN).write({self.campo: self.despues_json})
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'resuelta' if decision == 'resolver' else 'ignorada',
            'nota_resolucion': nota.strip(), 'resuelta_por_id': self.env.uid, 'fecha_resolucion': fields.Datetime.now()})
        self.activity_ids.action_feedback(feedback=nota)
        self.message_post(body='Incidencia %s: %s' % ('resuelta' if decision == 'resolver' else 'ignorada', nota))
        if self.procedimiento_id:
            self.procedimiento_id.message_post(body='Incidencia %s (%s) %s: %s' % (
                self.id, self.campo, 'resuelta' if decision == 'resolver' else 'ignorada', nota))
        return True

    def _apply_catalog(self, record, guardar_alias):
        model, fk, _groups = CATALOGS[self.campo]
        if not record or record._name != model or len(record) != 1 or not record.exists():
            raise ValidationError('Seleccione un registro del catálogo correspondiente.')
        record.check_access('read')
        if any(field in record._fields and not record[field] for field in ('active', 'activo')) or (self.campo == 'estatus_portal' and record.estado == 'inactivo'):
            raise ValidationError('Seleccione un registro activo del catálogo.')
        target = self.procedimiento_id
        lock(target)
        if target[fk].id != self.antes_json:
            raise UserError('El valor del procedimiento cambió. Revise la corrección antes de continuar.')
        if guardar_alias:
            if self.campo != 'entidad_federativa':
                raise ValidationError('Solo la entidad admite guardar el alias desde este asistente.')
            if ',' in (self.valor_encontrado or ''):
                raise ValidationError('El valor contiene comas; revise manualmente los alias del catálogo.')
            record.write({'nombres_alternativos': ', '.join(aliases(','.join(filter(None, [record.nombres_alternativos, self.valor_encontrado]))))})
        target.with_context(_lp_import=IMPORT_TOKEN).write({fk: record.id})

    def _cron_escalar(self):
        hours = int(self.env['ir.config_parameter'].sudo().get_param('licitaciones_publicas.escalamiento_horas', '24'))
        cutoff = fields.Datetime.now() - timedelta(hours=max(hours, 1))
        managers = self.env.ref('licitaciones_publicas.group_licitaciones_manager').sudo().all_user_ids.filtered('active')
        for rec in self.search([('state', '=', 'abierta'), ('severidad', '=', 'bloqueante'), ('create_date', '<=', cutoff), ('escalada_fecha', '=', False)]):
            lock(rec)
            if rec.escalada_fecha:
                continue
            companies = rec.procedimiento_id.company_ids if rec.procedimiento_id else rec.carga_id.company_ids
            eligible = managers.filtered(lambda u: not companies or bool(u.company_ids & companies))
            for manager in eligible:
                rec.activity_schedule('mail.mail_activity_data_todo', user_id=manager.id, summary='Incidencia bloqueante sin resolver')
            if eligible:
                rec.with_context(_lp_flow=FLOW_TOKEN).write({'escalada_fecha': fields.Datetime.now()})
