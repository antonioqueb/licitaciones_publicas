from datetime import timedelta

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError, ValidationError

from ..parser import DATE_FIELDS, identifier_parts, ImportValidationError
from .common import FLOW_TOKEN, imported, internal, lock, modal

STATES = [('detectado', 'Detectado'), ('analisis', 'En análisis'), ('preguntas', 'En preguntas'),
          ('costeo', 'Costeo'), ('propuesta', 'Propuesta'), ('con_fallo', 'Con fallo'),
          ('descartado', 'Descartado'), ('no_viable', 'No viable')]
NEXT = {'detectado': 'analisis', 'analisis': 'preguntas', 'preguntas': 'costeo',
        'costeo': 'propuesta', 'propuesta': 'con_fallo'}


class Procedimiento(models.Model):
    _name = 'licitacion.procedimiento'
    _description = 'Procedimiento de licitación pública'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'licitacion.retained']
    _rec_name = 'identificador'
    _order = 'fecha_apertura desc, identificador'

    identificador = fields.Char(required=True, index=True, copy=False, tracking=True)
    nombre_publicado = fields.Char(string='Nombre publicado', required=True, tracking=True)
    codigo_expediente = fields.Char(string='Código del expediente')
    tipo_procedimiento = fields.Char(string='Tipo', compute='_compute_identifier', store=True)
    caracter = fields.Selection([('N', 'Nacional'), ('I', 'Internacional'), ('T', 'TLC')], string='Carácter', compute='_compute_identifier', store=True)
    ordenamiento_legal = fields.Selection([('LAASSP', 'LAASSP'), ('LOPSRM', 'LOPSRM')], compute='_compute_identifier', store=True)
    consecutivo = fields.Char(compute='_compute_identifier', store=True)
    ejercicio = fields.Char(compute='_compute_identifier', store=True)
    unidad_compradora_id = fields.Many2one('licitacion.unidad.compradora', string='Unidad compradora', required=True, ondelete='restrict', tracking=True)
    entidad_id = fields.Many2one(related='unidad_compradora_id.entidad_id', store=True, string='Entidad')
    tipo_contratacion_id = fields.Many2one('licitacion.tipo.contratacion', string='Contratación', required=True, ondelete='restrict', tracking=True)
    fecha_junta_aclaraciones = fields.Datetime(string='Junta de aclaraciones', tracking=True)
    fecha_limite_preguntas = fields.Datetime(string='Límite de preguntas', tracking=True)
    fecha_entrega_muestras = fields.Datetime(string='Entrega de muestras', tracking=True)
    fecha_apertura = fields.Datetime(string='Apertura', tracking=True)
    fecha_fallo = fields.Datetime(string='Fallo', tracking=True)
    fecha_fallo_original = fields.Datetime(string='Fallo original', readonly=True)
    fallo_diferido = fields.Boolean(string='Fallo diferido', compute='_compute_fallo', store=True)
    estatus_portal_id = fields.Many2one('licitacion.estatus.portal', string='Estatus portal', readonly=True, ondelete='restrict', tracking=True)
    state = fields.Selection(STATES, string='Estado interno', default='detectado', required=True, tracking=True, group_expand='_read_group_state')
    motivo_descarte_id = fields.Many2one('licitacion.motivo.descarte', string='Motivo', tracking=True, ondelete='restrict')
    nota_criba = fields.Text(string='Nota de criba', tracking=True)
    user_id = fields.Many2one('res.users', string='Responsable', default=lambda s: s.env.user, required=True, tracking=True)
    active = fields.Boolean(string='Activo', default=True)
    primer_snapshot_id = fields.Many2one('licitacion.carga', readonly=True, ondelete='restrict')
    ultimo_snapshot_id = fields.Many2one('licitacion.carga', readonly=True, ondelete='restrict')
    sigue_apareciendo = fields.Boolean(string='Sigue apareciendo', default=True, readonly=True, tracking=True)
    fecha_ya_no_aparece = fields.Date(string='Ausente desde', readonly=True, tracking=True)
    reapertura_habilitada = fields.Boolean(readonly=True, copy=False)
    junta_72_fecha = fields.Datetime(readonly=True, copy=False)
    junta_24_fecha = fields.Datetime(readonly=True, copy=False)
    company_ids = fields.Many2many('res.company', compute='_compute_companies', store=True, string='Empresas participantes')
    partida_ids = fields.One2many('licitacion.partida', 'procedimiento_id', string='Renglones')
    expediente_ids = fields.One2many('licitacion.expediente', 'procedimiento_id', string='Expedientes')
    incidencia_ids = fields.One2many('licitacion.incidencia', 'procedimiento_id', string='Incidencias')
    aparicion_ids = fields.One2many('licitacion.aparicion', 'procedimiento_id', string='Historial de cargas')
    renglones_count = fields.Integer(compute='_compute_counts', string='Renglones')
    renglones_con_empresa_count = fields.Integer(compute='_compute_counts', string='Con empresa')
    renglones_descartados_count = fields.Integer(compute='_compute_counts', string='Descartados')
    incidencias_abiertas_count = fields.Integer(compute='_compute_counts', string='Incidencias abiertas')
    junta_class = fields.Selection([('sin_fecha', 'Sin fecha'), ('normal', 'Próxima'), ('urgente', 'En 72 h'), ('vencida', 'Vencida')], compute='_compute_junta', store=True, string='Semáforo')
    _identifier_unique = models.Constraint('UNIQUE(identificador)', 'El identificador debe ser único.')

    @api.depends('identificador')
    def _compute_identifier(self):
        for rec in self:
            try:
                values = identifier_parts(rec.identificador)
            except ImportValidationError:
                values = {k: False for k in ('tipo_procedimiento', 'caracter', 'ordenamiento_legal', 'consecutivo', 'ejercicio')}
            for key, value in values.items():
                rec[key] = value

    @api.constrains('identificador')
    def _check_identifier(self):
        for rec in self:
            try:
                identifier_parts(rec.identificador)
            except ImportValidationError as exc:
                raise ValidationError(str(exc)) from exc

    @api.depends('partida_ids.company_ids')
    def _compute_companies(self):
        for rec in self:
            rec.company_ids = rec.partida_ids.company_ids

    @api.depends('fecha_fallo', 'fecha_fallo_original')
    def _compute_fallo(self):
        for rec in self:
            rec.fallo_diferido = bool(rec.fecha_fallo_original and rec.fecha_fallo and rec.fecha_fallo > rec.fecha_fallo_original)

    @api.depends('fecha_junta_aclaraciones')
    def _compute_junta(self):
        now = fields.Datetime.now()
        for rec in self:
            delta = (rec.fecha_junta_aclaraciones - now).total_seconds() if rec.fecha_junta_aclaraciones else None
            rec.junta_class = 'sin_fecha' if delta is None else 'vencida' if delta < 0 else 'urgente' if delta <= 72 * 3600 else 'normal'

    @api.depends('partida_ids.company_ids', 'partida_ids.participacion', 'incidencia_ids.state')
    def _compute_counts(self):
        for rec in self:
            rec.renglones_count = len(rec.partida_ids)
            rec.renglones_con_empresa_count = len(rec.partida_ids.filtered('company_ids'))
            rec.renglones_descartados_count = len(rec.partida_ids.filtered(lambda p: p.participacion == 'descartada'))
            rec.incidencias_abiertas_count = len(rec.incidencia_ids.filtered(lambda i: i.state == 'abierta'))

    @api.model
    def _read_group_state(self, states, domain):
        return [key for key, label in STATES]

    @api.constrains('state', 'motivo_descarte_id')
    def _check_motivo(self):
        for rec in self:
            if rec.state in ('descartado', 'no_viable') and (not rec.motivo_descarte_id or rec.motivo_descarte_id.aplica_a not in ('procedimiento', 'ambos')):
                raise ValidationError('Seleccione un motivo de descarte aplicable a procedimientos.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['identificador'] = (vals.get('identificador') or '').strip().upper()
            if not imported(self.env) and any(k in vals or 'default_' + k in self.env.context for k in self._protected_fields()):
                raise AccessError('Solo la importación puede modificar los campos de trazabilidad y portal.')
            if vals.get('state', 'detectado') != 'detectado':
                raise ValidationError('Todo procedimiento comienza como Detectado.')
            vals.setdefault('state', 'detectado')
        return super().create(vals_list)

    def _protected_fields(self):
        return {'estatus_portal_id', 'primer_snapshot_id', 'ultimo_snapshot_id', 'sigue_apareciendo',
                'fecha_ya_no_aparece', 'fecha_fallo_original', 'reapertura_habilitada', 'company_ids'}

    def write(self, vals):
        if 'identificador' in vals:
            raise UserError('El identificador de un procedimiento es permanente.')
        if not imported(self.env) and self._protected_fields() & vals.keys():
            raise AccessError('Estos campos los administra la importación.')
        if 'state' in vals and not internal(self.env):
            raise UserError('Utilice las acciones de criba o avance para cambiar el estado interno.')
        return super().write(vals)

    def action_cribar(self):
        return modal(self.env['licitacion.criba.wizard'], {'procedimiento_ids': [Command.set(self.ids)]})

    def _cribar(self, decision, motivo=None, nota=None):
        lock(self)
        for rec in self:
            vals = {'nota_criba': nota or False}
            if decision in ('descartar', 'no_viable'):
                if not motivo or not motivo.active or motivo.aplica_a not in ('procedimiento', 'ambos'):
                    raise ValidationError('Seleccione un motivo de catálogo válido.')
                vals.update(state='descartado' if decision == 'descartar' else 'no_viable', motivo_descarte_id=motivo.id)
            elif decision in ('reabrir', 'participamos'):
                if rec.state == 'descartado' and not rec.reapertura_habilitada:
                    raise UserError('Para retomar un descartado, primero importe fechas límite nuevas del portal.')
                if decision == 'reabrir' and rec.state not in ('descartado', 'no_viable'):
                    raise UserError('Solo se puede reabrir un procedimiento cerrado por criba.')
                if decision == 'participamos' and rec.state not in ('detectado', 'descartado', 'no_viable'):
                    raise UserError('El procedimiento ya está en participación.')
                vals.update(state='detectado' if decision == 'reabrir' else 'analisis', motivo_descarte_id=False)
                if decision == 'reabrir':
                    rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.user_id.id, summary='Revisar procedimiento reabierto')
            else:
                raise ValidationError('Decisión desconocida.')
            from .common import IMPORT_TOKEN
            rec.with_context(_lp_flow=FLOW_TOKEN, _lp_import=IMPORT_TOKEN).write(dict(vals, reapertura_habilitada=False))
            rec.message_post(body='Nueva decisión de criba: %s. %s' % (dict(STATES)[vals['state']], nota or 'Sin nota adicional.'))
        return True

    def action_pasar_a_analisis(self):
        return self._cribar('participamos')

    def action_reabrir(self):
        return self.action_cribar()

    def action_avanzar(self):
        lock(self)
        for rec in self:
            nxt = NEXT.get(rec.state)
            if not nxt:
                raise UserError('No existe un siguiente estado para esta etapa.')
            if rec.state == 'analisis':
                raise UserError('Genere los expedientes para pasar a Preguntas.')
            if rec.incidencia_ids.filtered(lambda i: i.state == 'abierta' and i.severidad == 'bloqueante'):
                raise UserError('Resuelva las incidencias bloqueantes antes de avanzar.')
            rec.with_context(_lp_flow=FLOW_TOKEN).write({'state': nxt})
        return True

    def action_generar_expedientes(self):
        self.ensure_one()
        return modal(self.env['licitacion.generar.expedientes.wizard'], {'procedimiento_id': self.id})

    def action_open_expedientes(self):
        return {'type': 'ir.actions.act_window', 'name': 'Expedientes', 'res_model': 'licitacion.expediente',
                'view_mode': 'list,form', 'domain': [('procedimiento_id', 'in', self.ids)]}

    def action_open_incidencias(self):
        return {'type': 'ir.actions.act_window', 'name': 'Incidencias', 'res_model': 'licitacion.incidencia',
                'view_mode': 'list,form', 'domain': [('procedimiento_id', 'in', self.ids)]}

    def _cron_recordatorio_juntas(self, hours=72):
        now = fields.Datetime.now()
        if hours == 72:
            dated = self.search([('fecha_junta_aclaraciones', '!=', False)])
            self.env.add_to_compute(self._fields['junta_class'], dated)
            dated._recompute_recordset(['junta_class'])
        procedures = self.search([('state', 'not in', ['descartado', 'no_viable', 'con_fallo']),
                                 ('fecha_junta_aclaraciones', '>', now),
                                 ('fecha_junta_aclaraciones', '<=', now + timedelta(hours=hours))])
        marker = 'junta_72_fecha' if hours == 72 else 'junta_24_fecha'
        for rec in procedures:
            lock(rec)
            if rec[marker] == rec.fecha_junta_aclaraciones:
                continue
            if hours == 24 and (rec.junta_72_fecha != rec.fecha_junta_aclaraciones or not rec.activity_ids.filtered(lambda a: a.summary == 'Junta en 72 h')):
                continue
            rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.user_id.id,
                                  summary='Junta en %s h' % hours, date_deadline=fields.Date.context_today(rec))
            rec.message_post(body='Recordatorio al responsable: junta de aclaraciones en %s horas o menos.' % hours)
            rec.write({marker: rec.fecha_junta_aclaraciones})
