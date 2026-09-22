import hashlib

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError

from ..parser import digest
from .common import IMPORT_TOKEN, FLOW_TOKEN, imported, internal, lock, modal
from .importer import LicitacionImporter


class Carga(models.Model):
    _name = 'licitacion.carga'
    _description = 'Carga versionada del portal'
    _inherit = ['mail.thread', 'licitacion.retained']
    _order = 'fecha_snapshot desc, id desc'
    _rec_name = 'archivo_nombre'

    archivo = fields.Binary(string='Excel original', required=True, attachment=True)
    archivo_nombre = fields.Char(string='Archivo', required=True)
    fecha_snapshot = fields.Date(string='Fecha del snapshot', required=True)
    origen_portal = fields.Selection([('comprasmx', 'ComprasMX')], string='Origen', default='comprasmx', required=True)
    alcance = fields.Char(string='Alcance de la búsqueda', default='general', required=True,
                         help='Use el mismo nombre solo para exportaciones con los mismos filtros del portal.')
    zona_horaria = fields.Char(string='Zona horaria del Excel', default='America/Mexico_City', required=True)
    tipo_detectado = fields.Selection([('listado', 'Listado de procedimientos'), ('detalle', 'Detalle de partidas')], string='Tipo detectado', readonly=True, required=True)
    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', ondelete='restrict')
    nota_asignacion = fields.Text(string='Justificación de asignación manual')
    company_ids = fields.Many2many('res.company', string='Empresas del alcance', required=True, default=lambda s: s.env.companies)
    scope_key = fields.Char(compute='_compute_scope', store=True, index=True)
    state = fields.Selection([('borrador', 'Borrador'), ('previsualizada', 'Previsualizada'), ('confirmada', 'Confirmada'),
                              ('rechazada', 'Rechazada'), ('pendiente_asignacion', 'Pendiente de asignación')],
                             string='Estado', default='borrador', required=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Cargado por', default=lambda s: s.env.user, readonly=True, required=True)
    prepared_json = fields.Json(readonly=True, copy=False)
    present_keys = fields.Json(readonly=True, copy=False)
    fingerprint = fields.Char(readonly=True, copy=False)
    procedimientos_nuevos = fields.Integer(readonly=True, string='Procedimientos nuevos')
    procedimientos_cambios = fields.Integer(readonly=True, string='Procedimientos con cambios')
    procedimientos_sin_cambios = fields.Integer(readonly=True, string='Procedimientos sin cambios')
    procedimientos_gone = fields.Integer(readonly=True, string='Procedimientos ausentes')
    partidas_nuevas = fields.Integer(readonly=True, string='Partidas nuevas')
    partidas_cambios = fields.Integer(readonly=True, string='Partidas con cambios')
    partidas_sin_cambios = fields.Integer(readonly=True, string='Partidas sin cambios')
    partidas_gone = fields.Integer(readonly=True, string='Partidas ausentes')
    registros = fields.Integer(compute='_compute_resumen', string='Registros')
    resumen = fields.Char(compute='_compute_resumen', string='Resumen')
    aparicion_ids = fields.One2many('licitacion.aparicion', 'carga_id', string='Apariciones')
    incidencia_ids = fields.One2many('licitacion.incidencia', 'carga_id', string='Incidencias')

    @api.depends('origen_portal', 'alcance', 'tipo_detectado', 'procedimiento_id', 'company_ids')
    def _compute_scope(self):
        for rec in self:
            rec.scope_key = digest([rec.origen_portal, (rec.alcance or '').strip(), rec.tipo_detectado,
                                    rec.procedimiento_id.id, sorted(rec.company_ids.ids)])

    @api.depends('prepared_json')
    def _compute_resumen(self):
        for rec in self:
            diff = (rec.prepared_json or {}).get('diff', {})
            counts = [len(diff.get(k, [])) for k in ('nuevos', 'cambios', 'sin_cambios', 'gone')]
            rec.registros = sum(counts[:3])
            rec.resumen = 'Nuevos: %s · Cambios: %s · Sin cambios: %s · Ya no aparecen: %s' % tuple(counts)

    @api.model_create_multi
    def create(self, vals_list):
        if not internal(self.env):
            raise AccessError('Utilice Nueva carga para subir y validar el archivo.')
        return super().create(vals_list)

    def write(self, vals):
        if not internal(self.env):
            raise AccessError('La carga se administra a través de sus asistentes.')
        if any(r.state in ('confirmada', 'rechazada') for r in self):
            raise UserError('Una carga cerrada es inmutable. Genere una nueva versión.')
        return super().write(vals)

    def _prepare(self):
        self.ensure_one()
        lock(self)
        if self.state in ('confirmada', 'rechazada'):
            raise UserError('Esta carga ya está cerrada.')
        importer = LicitacionImporter.for_carga(self)
        prepared = importer.compute_diff(self)
        prefix = 'procedimientos' if self.tipo_detectado == 'listado' else 'partidas'
        vals = {'prepared_json': prepared, 'fingerprint': prepared['fingerprint'], 'state': 'previsualizada'}
        for category, entries in prepared['diff'].items():
            vals[prefix + '_' + ('nuevos' if category == 'nuevos' else category)] = len(entries)
        # Singular model names use *_nuevas for partidas.
        if 'partidas_nuevos' in vals:
            vals['partidas_nuevas'] = vals.pop('partidas_nuevos')
        self.with_context(_lp_flow=FLOW_TOKEN).write(vals)
        return self._open_preview()

    def _open_preview(self):
        self.ensure_one()
        return modal(self.env['licitacion.preview.wizard'], {'carga_id': self.id}, persist=True)

    def action_preview(self):
        return self._prepare()

    def action_asignar(self):
        self.ensure_one()
        if self.state != 'pendiente_asignacion':
            raise UserError('Esta carga no está pendiente de asignación.')
        return modal(self.env['licitacion.asignar.procedimiento.wizard'], {'carga_id': self.id})

    def _confirm(self):
        self.ensure_one()
        lock(self)
        if self.state == 'confirmada':
            return True
        if self.state != 'previsualizada':
            raise UserError('Primero previsualice la carga.')
        # Serializes this scope without taking record locks on other companies.
        key = int(self.scope_key[:15], 16)
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [key])
        importer = LicitacionImporter.for_carga(self)
        fresh = importer.compute_diff(self)
        if fresh['fingerprint'] != self.fingerprint:
            raise UserError('Los datos cambiaron desde la previsualización. Vuelva a previsualizar antes de confirmar.')
        importer.commit(fresh, self)
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'confirmada', 'present_keys': fresh['present_keys']})
        self.message_post(body='Importación confirmada por %s. %s' % (self.env.user.display_name, self.resumen))
        return True

    def action_rechazar(self):
        lock(self)
        if any(r.state in ('confirmada', 'rechazada') for r in self):
            raise UserError('Esta carga ya está cerrada.')
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'rechazada'})


class Aparicion(models.Model):
    _name = 'licitacion.aparicion'
    _description = 'Snapshot inmutable de procedimiento'
    _inherit = 'licitacion.retained'
    _order = 'carga_id desc'

    procedimiento_id = fields.Many2one('licitacion.procedimiento', required=True, ondelete='restrict', index=True)
    carga_id = fields.Many2one('licitacion.carga', required=True, ondelete='restrict', index=True)
    presente = fields.Boolean(string='Presente en archivo', default=True)
    datos_snapshot = fields.Json(string='Datos originales', required=True)
    nombre_publicado_snapshot = fields.Char(string='Nombre publicado')
    estatus_portal_id_snapshot = fields.Many2one('licitacion.estatus.portal', string='Estatus portal', ondelete='restrict')
    unidad_compradora_id_snapshot = fields.Many2one('licitacion.unidad.compradora', string='Unidad compradora', ondelete='restrict')
    fecha_junta_snapshot = fields.Datetime(string='Junta')
    fecha_apertura_snapshot = fields.Datetime(string='Apertura')
    fecha_fallo_snapshot = fields.Datetime(string='Fallo')
    _snapshot_unique = models.Constraint('UNIQUE(procedimiento_id, carga_id)', 'Ya existe este snapshot.')

    @api.model_create_multi
    def create(self, vals_list):
        if not imported(self.env):
            raise AccessError('Los snapshots se crean al confirmar una carga.')
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError('Los snapshots son inmutables.')
