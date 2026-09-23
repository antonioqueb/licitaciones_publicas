import hashlib
import re

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError

from ..parser import digest, ImportValidationError
from ..file_identity import uploaded_file
from .common import IMPORT_TOKEN, FLOW_TOKEN, imported, internal, lock, modal
from .importer import LicitacionImporter
from .tipo_archivo import TIPOS_DATO


class Carga(models.Model):
    _name = 'licitacion.carga'
    _description = 'Carga versionada del portal'
    _inherit = ['mail.thread', 'licitacion.retained']
    _order = 'fecha_snapshot desc, id desc'
    _rec_name = 'archivo_nombre'

    archivo = fields.Binary(string='Excel original', required=True, attachment=True)
    archivo_nombre = fields.Char(string='Archivo', required=True)
    binary_sha256 = fields.Char(string='Huella SHA-256 del archivo', compute='_compute_binary_sha256',
                                store=True, index=True, copy=False,
                                help='Identidad del binario original. Se calcula también para las cargas históricas.')
    reimportacion_forzada = fields.Boolean(string='Reimportación forzada', readonly=True, copy=False)
    motivo_reimportacion = fields.Text(string='Motivo de reimportación', readonly=True, copy=False)
    cargas_origen_ids = fields.Many2many('licitacion.carga', 'licitacion_carga_reimportacion_rel',
                                       'carga_id', 'origen_id', string='Cargas anteriores', readonly=True, copy=False)
    fecha_confirmacion = fields.Datetime(string='Confirmada el', readonly=True, copy=False)
    confirmada_por_id = fields.Many2one('res.users', string='Confirmada por', readonly=True, copy=False)
    procesado_el = fields.Datetime(string='Procesado el', compute='_compute_processing')
    procesado_por_id = fields.Many2one('res.users', string='Procesado por', compute='_compute_processing')
    coincidencias_ids = fields.Many2many('licitacion.carga', compute='_compute_coincidencias', string='Cargas confirmadas del mismo archivo')
    coincidencias_count = fields.Integer(compute='_compute_coincidencias', string='Coincidencias')
    carga_base_id = fields.Many2one('licitacion.carga', string='Carga confirmada de referencia', readonly=True, copy=False)
    aviso_base = fields.Text(string='Referencia de comparación', readonly=True, copy=False)
    fecha_snapshot = fields.Date(string='Fecha del snapshot', required=True)
    origen_portal = fields.Selection([('comprasmx', 'ComprasMX')], string='Origen', default='comprasmx', required=True)
    alcance = fields.Char(string='Alcance de la búsqueda', default='general', required=True,
                         help='Use el mismo nombre solo para exportaciones con los mismos filtros del portal.')
    zona_horaria = fields.Char(string='Zona horaria del Excel', default='America/Mexico_City', required=True)
    tipo_detectado = fields.Selection([('listado', 'Listado de procedimientos'), ('detalle', 'Detalle de partidas'), ('catalogo', 'Catálogo SAI'), ('anexo', 'Anexo')], string='Tipo detectado', readonly=True, required=True)
    tipo_archivo_id = fields.Many2one('licitacion.tipo.archivo', string='Formato detectado', readonly=True, ondelete='restrict')
    subtipo_detectado = fields.Selection(TIPOS_DATO, string='Subtipo', readonly=True)
    configuracion_snapshot = fields.Json(string='Configuración utilizada', readonly=True)
    detalle_borrador = fields.Boolean(string='Detalle en borrador', compute='_compute_borrador')
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

    @api.depends('archivo')
    def _compute_binary_sha256(self):
        for rec in self.with_context(bin_size=False):
            # Stored computation also backfills existing uploads at upgrade,
            # without changing their state, snapshots or write metadata.
            try:
                rec.binary_sha256 = uploaded_file(rec.archivo)[1] if rec.archivo else False
            except ImportValidationError as exc:
                raise UserError(str(exc)) from exc

    @api.depends('fecha_confirmacion', 'confirmada_por_id', 'create_date', 'user_id')
    def _compute_processing(self):
        for rec in self:
            rec.procesado_el = rec.fecha_confirmacion or rec.create_date
            rec.procesado_por_id = rec.confirmada_por_id or rec.user_id or rec.create_uid

    @api.model
    def _confirmed_file(self, sha, exclude_id=False):
        if not sha:
            return self.browse()
        # Never sudo: the upload must not disclose another company's history.
        return self.search([('binary_sha256', '=', sha.lower()), ('state', '=', 'confirmada'),
                            ('id', '!=', exclude_id or 0)], order='id desc')

    @api.depends('binary_sha256', 'state')
    @api.depends_context('uid', 'company')
    def _compute_coincidencias(self):
        for rec in self:
            matches = self._confirmed_file(rec.binary_sha256)
            rec.coincidencias_ids = matches
            rec.coincidencias_count = len(matches)

    def action_open(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'current'}

    @api.depends('tipo_detectado')
    def _compute_borrador(self):
        for rec in self:
            rec.detalle_borrador = rec.tipo_detectado == 'detalle'

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
        vals = {'prepared_json': prepared, 'fingerprint': prepared['fingerprint'], 'state': 'previsualizada',
                'tipo_archivo_id': importer.tipo_archivo_id, 'subtipo_detectado': importer.subtipo,
                'configuracion_snapshot': importer.config,
                'carga_base_id': prepared.get('previous_id'), 'aviso_base': prepared.get('aviso_base')}
        for category, entries in prepared['diff'].items():
            if self.tipo_detectado in ('listado', 'detalle'):
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
        self.env['licitacion.archivo.huella']._serialize(self.binary_sha256)
        previous = self._confirmed_file(self.binary_sha256, self.id)
        if previous and not self.reimportacion_forzada:
            raise UserError('Este archivo ya fue procesado en la carga %s. Abra la carga existente o use Forzar re-importación con motivo.' % previous[0].display_name)
        if self.reimportacion_forzada and not (self.motivo_reimportacion or '').strip():
            raise UserError('La reimportación forzada requiere un motivo.')
        # Serializes this scope without taking record locks on other companies.
        key = int(digest('catalogo-sai-global')[:15], 16) if self.tipo_detectado == 'catalogo' else int(self.scope_key[:15], 16)
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [key])
        importer = LicitacionImporter.for_carga(self)
        fresh = importer.compute_diff(self)
        if fresh['fingerprint'] != self.fingerprint:
            raise UserError('Los datos cambiaron desde la previsualización. Vuelva a previsualizar antes de confirmar.')
        importer.commit(fresh, self)
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'confirmada', 'present_keys': fresh['present_keys'],
                'fecha_confirmacion': fields.Datetime.now(), 'confirmada_por_id': self.env.uid})
        self.message_post(body='Importación confirmada por %s. %s' % (self.env.user.display_name, self.resumen))
        return True

    def action_rechazar(self):
        lock(self)
        if any(r.state in ('confirmada', 'rechazada') for r in self):
            raise UserError('Esta carga ya está cerrada.')
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'rechazada'})


class ArchivoHuella(models.Model):
    _name = 'licitacion.archivo.huella'
    _description = 'Control transaccional de archivos de licitaciones'
    _log_access = False

    binary_sha256 = fields.Char(required=True, readonly=True)
    revision = fields.Integer(readonly=True)
    _sha_unique = models.Constraint('UNIQUE(binary_sha256)', 'La huella del control debe ser única.')

    @api.model
    def _serialize(self, sha):
        if not re.fullmatch('[0-9a-f]{64}', sha or ''):
            raise UserError('No se pudo calcular la huella del archivo.')
        # A real row write (not just an advisory lock) invalidates concurrent
        # REPEATABLE READ snapshots. Odoo retries SerializationFailure from RPC
        # and the retried request sees the first committed upload.
        self.env.cr.execute('''INSERT INTO licitacion_archivo_huella (binary_sha256, revision)
            VALUES (%s, 1) ON CONFLICT (binary_sha256) DO UPDATE
            SET revision = licitacion_archivo_huella.revision + 1''', [sha])


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
