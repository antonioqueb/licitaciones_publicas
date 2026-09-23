import json

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError, ValidationError

from ..models.common import FLOW_TOKEN, internal, lock, require_companies, modal
from ..models.importer import LicitacionImporter
from ..file_identity import uploaded_file
from ..parser import digest, ImportValidationError


def close():
    return {'type': 'ir.actions.act_window_close'}


class CargaWizard(models.TransientModel):
    _name = 'licitacion.carga.wizard'
    _description = 'Subir Excel del portal'

    archivo = fields.Binary(string='Archivo Excel', required=True)
    archivo_nombre = fields.Char(string='Nombre del archivo', required=True)
    fecha_snapshot = fields.Date(string='Fecha del snapshot', required=True, default=fields.Date.context_today)
    origen_portal = fields.Selection([('comprasmx', 'ComprasMX')], string='Origen', required=True, default='comprasmx')
    alcance = fields.Char(string='Alcance de búsqueda', default='general', required=True,
                         help='Nombre estable de los filtros usados en el portal. Solo se comparan cargas del mismo alcance.')
    zona_horaria = fields.Char(string='Zona horaria del Excel', default='America/Mexico_City', required=True)
    tipo_detectado = fields.Char(string='Tipo detectado', readonly=True)
    detalle_borrador = fields.Boolean(string='Detalle en borrador', readonly=True)
    cargas_previas_ids = fields.Many2many('licitacion.carga', compute='_compute_previas', string='Coincidencias confirmadas')
    carga_previa_id = fields.Many2one('licitacion.carga', string='Carga a consultar')
    previa_snapshot = fields.Date(related='carga_previa_id.fecha_snapshot', string='Fecha snapshot', compute_sudo=False)
    previa_procesada = fields.Datetime(related='carga_previa_id.procesado_el', string='Procesado el', compute_sudo=False)
    previa_usuario_id = fields.Many2one(related='carga_previa_id.procesado_por_id', string='Procesado por', compute_sudo=False)
    previa_resumen = fields.Char(related='carga_previa_id.resumen', string='Resumen', compute_sudo=False)
    previa_state = fields.Selection(related='carga_previa_id.state', string='Estado', compute_sudo=False)
    carga_id = fields.Many2one('licitacion.carga', readonly=True, copy=False)
    request_fingerprint = fields.Char(readonly=True, copy=False)

    def _check_previous_access(self, previous_id):
        # Odoo 19 runs @api.constrains in sudo mode. Permissions must be
        # checked at the operation boundary, in the caller's environment.
        if previous_id:
            self.env['licitacion.carga'].browse(previous_id).check_access('read')

    @api.constrains('carga_previa_id', 'archivo')
    def _check_selected_previous(self):
        for rec in self:
            if rec.carga_previa_id:
                if rec.carga_previa_id not in rec.env['licitacion.carga']._confirmed_file(rec._file()[1]):
                    raise ValidationError('La carga seleccionada debe corresponder a este archivo confirmado.')

    @api.model_create_multi
    def create(self, vals_list):
        if not internal(self.env) and any({'carga_id', 'request_fingerprint'} & vals.keys() for vals in vals_list):
            raise AccessError('La carga asociada la determina el asistente.')
        previous_default = self.default_get(['carga_previa_id']).get('carga_previa_id', False)
        for vals in vals_list:
            # Untrusted default_* context must not inject a cached result.
            vals.setdefault('carga_id', False)
            vals.setdefault('request_fingerprint', False)
            vals.setdefault('carga_previa_id', previous_default)
            self._check_previous_access(vals['carga_previa_id'])
        return super().create(vals_list)

    def write(self, vals):
        if not internal(self.env) and {'carga_id', 'request_fingerprint'} & vals.keys():
            raise AccessError('La carga asociada la determina el asistente.')
        if 'carga_previa_id' in vals:
            self._check_previous_access(vals['carga_previa_id'])
        return super().write(vals)

    @api.onchange('carga_previa_id')
    def _onchange_previous(self):
        # Onchange uses unsaved records and does not invoke create/write.
        for rec in self:
            rec._check_previous_access(rec.carga_previa_id.id)
        self._check_selected_previous()

    def _file(self):
        self.ensure_one()
        try:
            return uploaded_file(self.with_context(bin_size=False).archivo)
        except ImportValidationError as exc:
            raise UserError(str(exc)) from exc

    def _request_key(self, sha):
        return digest([sha, self.archivo_nombre, str(self.fecha_snapshot), self.origen_portal,
                       (self.alcance or '').strip(), self.zona_horaria, sorted(self.env.companies.ids)])

    @api.depends('archivo')
    @api.depends_context('uid', 'company')
    def _compute_previas(self):
        for rec in self:
            rec.cargas_previas_ids = rec.env['licitacion.carga']._confirmed_file(rec._file()[1]) if rec.archivo else False

    def _reader(self):
        self.ensure_one()
        content, _sha = self._file()
        return LicitacionImporter(self.env, content, self.archivo_nombre or '', self.zona_horaria)

    @api.onchange('archivo', 'archivo_nombre')
    def _onchange_file(self):
        self.tipo_detectado = False
        self.detalle_borrador = False
        self.carga_previa_id = False
        if self.archivo and self.archivo_nombre:
            previous = self.env['licitacion.carga']._confirmed_file(self._file()[1])
            self.cargas_previas_ids = previous
            if previous:
                self.carga_previa_id = previous[:1]
                return
            reader = self._reader()
            self.tipo_detectado = reader.config['name']
            self.detalle_borrador = reader.tipo == 'detalle'

    def action_preview(self):
        return self._preview()

    def action_open_existing(self):
        self.ensure_one()
        self.check_access('read')
        previous = self.env['licitacion.carga']._confirmed_file(self._file()[1])
        selected = self.carga_previa_id or previous[:1]
        if not selected or selected not in previous:
            raise UserError('Seleccione una carga confirmada de este mismo archivo.')
        return selected.action_open()

    def action_force(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env['licitacion.carga']._confirmed_file(self._file()[1]):
            raise UserError('Este archivo no tiene una carga confirmada previa. Use Previsualizar cambios.')
        return modal(self.env['licitacion.forzar.carga.wizard'], {'carga_wizard_id': self.id})

    def _preview(self, *, force_reason=None, expected_request=None):
        self.ensure_one()
        lock(self)
        _content, sha = self._file()
        request = self._request_key(sha)
        if expected_request is not None and request != expected_request:
            raise UserError('Cambió el archivo o su alcance. Cierre la confirmación avanzada y vuelva a solicitarla.')
        if self.carga_id and self.request_fingerprint == request:
            self.carga_id.check_access('read')
            require_companies(self.carga_id, self.carga_id.company_ids)
            if self.carga_id.state == 'previsualizada':
                return self.carga_id._open_preview()
            if self.carga_id.state == 'pendiente_asignacion':
                return self.carga_id.action_asignar()
            return self.carga_id.action_open()
        self.env['licitacion.archivo.huella']._serialize(sha)
        previous = self.env['licitacion.carga']._confirmed_file(sha)
        if previous and not force_reason:
            self.carga_previa_id = previous[:1]
            self.invalidate_recordset(['cargas_previas_ids'])
            return {'type': 'ir.actions.act_window', 'res_model': self._name,
                    'res_id': self.id, 'view_mode': 'form', 'target': 'new'}
        if self.env['ir.attachment']._storage() != 'file':
            raise UserError('Configure ir_attachment.location=file y un filestore persistente antes de cargar archivos.')
        reader = self._reader()
        procedure = self.env['licitacion.procedimiento']
        if reader.tipo == 'detalle' and reader.identifier:
            procedure = procedure.with_context(active_test=False).search([('identificador', '=', reader.identifier)], limit=1)
            if not procedure and procedure.sudo().search_count([('identificador', '=', reader.identifier)]):
                raise AccessError('El procedimiento pertenece a empresas no activas o no autorizadas.')
        vals = {'archivo': self.archivo, 'archivo_nombre': self.archivo_nombre, 'fecha_snapshot': self.fecha_snapshot,
                'origen_portal': self.origen_portal, 'alcance': self.alcance.strip(), 'zona_horaria': self.zona_horaria,
                'tipo_detectado': reader.tipo, 'procedimiento_id': procedure.id,
                'tipo_archivo_id': reader.tipo_archivo_id, 'subtipo_detectado': reader.subtipo,
                'configuracion_snapshot': reader.config,
                'state': 'borrador', 'reimportacion_forzada': False,
                'motivo_reimportacion': False, 'cargas_origen_ids': [Command.clear()],
                'fecha_confirmacion': False, 'confirmada_por_id': False,
                'company_ids': [Command.set(self.env.companies.ids)]}
        if force_reason:
            vals.update(reimportacion_forzada=True, motivo_reimportacion=force_reason.strip(),
                        cargas_origen_ids=[Command.set(previous.ids)])
        if not vals['alcance']:
            raise ValidationError('Indique un alcance de búsqueda.')
        if reader.tipo == 'detalle' and not procedure:
            vals['state'] = 'pendiente_asignacion'
        carga = self.env['licitacion.carga'].with_context(_lp_flow=FLOW_TOKEN).create(vals)
        self.with_context(_lp_flow=FLOW_TOKEN).write({'carga_id': carga.id, 'request_fingerprint': request})
        if force_reason:
            carga.message_post(body='Reimportación forzada por %s. Motivo: %s. Cargas anteriores: %s. SHA-256: %s.' % (
                self.env.user.display_name, force_reason.strip(), ', '.join(map(str, previous.ids)), sha))
        return carga.action_asignar() if carga.state == 'pendiente_asignacion' else carga._prepare()


class ForzarCarga(models.TransientModel):
    _name = 'licitacion.forzar.carga.wizard'
    _description = 'Confirmar reimportación de archivo procesado'

    carga_wizard_id = fields.Many2one('licitacion.carga.wizard', string='Archivo a reimportar', required=True, readonly=True, ondelete='cascade')
    motivo = fields.Text(string='Motivo de reimportación', required=True)
    confirmado = fields.Boolean(string='Confirmo que deseo procesar nuevamente este archivo')
    expected_request = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            wizard = self.env['licitacion.carga.wizard'].browse(
                vals.get('carga_wizard_id') or self.env.context.get('default_carga_wizard_id')).exists()
            if not wizard:
                raise UserError('Vuelva a abrir la carga antes de confirmar la reimportación.')
            wizard.check_access('write')
            vals['carga_wizard_id'] = wizard.id
            vals['expected_request'] = wizard._request_key(wizard._file()[1])
        return super().create(vals_list)

    def write(self, vals):
        if {'carga_wizard_id', 'expected_request'} & vals.keys():
            raise AccessError('La confirmación pertenece al archivo original.')
        return super().write(vals)

    def action_confirm(self):
        self.ensure_one()
        self.check_access('write')
        if not self.confirmado or not (self.motivo or '').strip():
            raise UserError('Confirme explícitamente la reimportación e indique un motivo.')
        return self.carga_wizard_id._preview(force_reason=self.motivo, expected_request=self.expected_request)


class AsignarProcedimiento(models.TransientModel):
    _name = 'licitacion.asignar.procedimiento.wizard'
    _description = 'Asignar detalle a procedimiento existente'

    carga_id = fields.Many2one('licitacion.carga', string='Carga', required=True, readonly=True)
    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', required=True)
    nota = fields.Text(string='Justificación', required=True)

    def action_asignar(self):
        self.ensure_one()
        lock(self.carga_id)
        self.procedimiento_id.check_access('write')
        if self.carga_id.state != 'pendiente_asignacion' or not (self.nota or '').strip():
            raise UserError('Seleccione un procedimiento y justifique la asignación pendiente.')
        self.carga_id.with_context(_lp_flow=FLOW_TOKEN).write({'procedimiento_id': self.procedimiento_id.id, 'nota_asignacion': self.nota, 'state': 'borrador'})
        return self.carga_id._prepare()


class Preview(models.TransientModel):
    _name = 'licitacion.preview.wizard'
    _description = 'Previsualización de importación'

    carga_id = fields.Many2one('licitacion.carga', string='Carga', required=True, readonly=True)
    resumen = fields.Char(related='carga_id.resumen')
    carga_base_id = fields.Many2one(related='carga_id.carga_base_id')
    aviso_base = fields.Text(related='carga_id.aviso_base')
    detalle_borrador = fields.Boolean(related='carga_id.detalle_borrador')
    line_ids = fields.One2many('licitacion.preview.line', 'wizard_id', readonly=True)
    nuevos_ids = fields.One2many('licitacion.preview.line', 'wizard_id', domain=[('categoria', '=', 'nuevos')], readonly=True)
    cambios_ids = fields.One2many('licitacion.preview.line', 'wizard_id', domain=[('categoria', '=', 'cambios')], readonly=True)
    sin_cambios_ids = fields.One2many('licitacion.preview.line', 'wizard_id', domain=[('categoria', '=', 'sin_cambios')], readonly=True)
    gone_ids = fields.One2many('licitacion.preview.line', 'wizard_id', domain=[('categoria', '=', 'gone')], readonly=True)
    advertencias = fields.Text(string='Incidencias que se registrarán', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            carga = self.env['licitacion.carga'].browse(vals['carga_id'])
            carga.check_access('read')
            if carga.state != 'previsualizada':
                raise UserError('La carga no tiene previsualización disponible.')
            prepared = carga.prepared_json or {}
            vals['line_ids'] = []
            for category, entries in prepared.get('diff', {}).items():
                for entry in entries:
                    data = entry['values']
                    vals['line_ids'].append(Command.create({'categoria': category,
                        'clave': data.get('identificador') or data.get('code') or '%s · %s' % (data.get('numero', ''), data.get('clave_cucop', '')),
                        'descripcion': data.get('nombre_publicado') or data.get('name') or data.get('descripcion_detallada', ''),
                        'detalle': json.dumps(entry.get('diff') or data, ensure_ascii=False, indent=2)}))
            messages = []
            for issue in prepared.get('congruencia', []):
                message = '[%s] %s · %s: %s → %s' % (
                    issue['severidad'].capitalize(), issue.get('identificador_observado') or issue.get('target_identificador') or carga.procedimiento_id.identificador,
                    issue['campo'], issue['valor_esperado'], issue['valor_encontrado'])
                if carga.tipo_detectado == 'listado' and issue['campo'] in ('prefijo_identificador', 'caracter_identificador'):
                    message += '. Esta fila no se creará ni actualizará hasta completar el catálogo y volver a importar.'
                messages.append(message)
            vals['advertencias'] = '\n'.join(messages)
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        self.carga_id._confirm()
        return {'type': 'ir.actions.act_window', 'res_model': 'licitacion.carga', 'res_id': self.carga_id.id, 'view_mode': 'form'}

    def action_rechazar(self):
        self.ensure_one()
        self.carga_id.action_rechazar()
        return close()


class PreviewLine(models.TransientModel):
    _name = 'licitacion.preview.line'
    _description = 'Fila de previsualización'

    wizard_id = fields.Many2one('licitacion.preview.wizard', required=True, ondelete='cascade')
    categoria = fields.Selection([('nuevos', 'Nuevos'), ('cambios', 'Cambios'), ('sin_cambios', 'Sin cambios'), ('gone', 'Ya no aparecen')], required=True)
    clave = fields.Char(string='Registro')
    descripcion = fields.Text(string='Descripción')
    detalle = fields.Text(string='Diferencias campo a campo')


class Criba(models.TransientModel):
    _name = 'licitacion.criba.wizard'
    _description = 'Criba individual o en lote'

    procedimiento_ids = fields.Many2many('licitacion.procedimiento', string='Procedimientos', required=True,
        default=lambda s: s.env.context.get('active_ids', []) if s.env.context.get('active_model') == 'licitacion.procedimiento' else [])
    es_lote = fields.Boolean(string='En lote', compute='_compute_lote')
    decision = fields.Selection([('participamos', 'Participamos'), ('descartar', 'Descartar'), ('no_viable', 'No viable'), ('reabrir', 'Reabrir')], string='Decisión', required=True, default='participamos')
    motivo_id = fields.Many2one('licitacion.motivo.descarte', string='Motivo', domain=[('aplica_a', 'in', ['procedimiento', 'ambos'])])
    nota = fields.Text(string='Nota')

    @api.depends('procedimiento_ids')
    def _compute_lote(self):
        for rec in self:
            rec.es_lote = len(rec.procedimiento_ids) > 1

    def action_apply(self):
        self.ensure_one()
        if not self.procedimiento_ids:
            raise ValidationError('Seleccione al menos un procedimiento.')
        self.procedimiento_ids._cribar(self.decision, self.motivo_id, self.nota)
        return close()


class GenerarExpedientes(models.TransientModel):
    _name = 'licitacion.generar.expedientes.wizard'
    _description = 'Confirmar expedientes y cartas por empresa'

    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', required=True, readonly=True)
    resumen = fields.Text(compute='_compute_resumen', string='Empresas, partidas y proveedores')

    @api.depends('procedimiento_id.partida_ids.company_ids', 'procedimiento_id.partida_ids.partida_proveedor_ids')
    def _compute_resumen(self):
        for rec in self:
            rec.resumen = '\n'.join('%s: %s partidas · %s proveedores' % (
                company.name, len(rec.procedimiento_id.partida_ids.filtered(lambda p: company in p.company_ids)),
                len(rec.procedimiento_id.partida_ids.filtered(lambda p: company in p.company_ids).partida_proveedor_ids.partner_id))
                for company in rec.procedimiento_id.company_ids)

    def action_generate(self):
        self.ensure_one()
        procedure = self.procedimiento_id
        lock(procedure)
        require_companies(self, procedure.sudo().company_ids)
        if procedure.state not in ('analisis', 'preguntas'):
            raise UserError('El procedimiento debe estar En análisis o En preguntas.')
        if procedure.incidencia_ids.filtered(lambda i: i.state == 'abierta' and i.severidad == 'bloqueante'):
            raise UserError('Resuelva las incidencias bloqueantes antes de generar expedientes.')
        if not procedure.company_ids or not procedure.partida_ids.filtered('company_ids').partida_proveedor_ids:
            raise UserError('Asigne al menos una empresa y un proveedor en sus partidas.')
        expedientes = self.env['licitacion.expediente']
        for company in procedure.company_ids.sorted('id'):
            model = expedientes.with_context(active_test=False).with_company(company)
            exp = model.search([('procedimiento_id', '=', procedure.id), ('company_id', '=', company.id)], limit=1)
            if not exp:
                exp = model.create({'procedimiento_id': procedure.id, 'company_id': company.id})
            expedientes |= exp
            for partner in exp.proveedor_ids:
                cartas = self.env['licitacion.carta.apoyo'].with_company(company)
                if not cartas.search_count([('expediente_id', '=', exp.id), ('partner_id', '=', partner.id)]):
                    cartas.create({'expediente_id': exp.id, 'partner_id': partner.id})
        if procedure.state == 'analisis':
            procedure.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'preguntas'})
        return {'type': 'ir.actions.act_window', 'res_model': 'licitacion.expediente',
                'res_id': expedientes[0].id, 'view_mode': 'form'}


class Resolver(models.TransientModel):
    _name = 'licitacion.resolver.incidencia.wizard'
    _description = 'Resolver o ignorar incidencia'

    incidencia_id = fields.Many2one('licitacion.incidencia', string='Incidencia', required=True, readonly=True)
    decision = fields.Selection([('resolver', 'Resolver y aplicar valor propuesto'), ('ignorar', 'Ignorar y conservar valor actual')], string='Decisión', required=True)
    nota = fields.Text(string='Justificación', required=True)

    def action_apply(self):
        self.ensure_one()
        self.incidencia_id._resolve(self.decision, self.nota)
        return close()


class PropagarEmpresas(models.TransientModel):
    _name = 'licitacion.propagar.empresas.wizard'
    _description = 'Propagar empresas conservando orden'

    partida_ids = fields.Many2many('licitacion.partida', string='Partidas seleccionadas', required=True)
    fuente_id = fields.Many2one('licitacion.partida', string='Partida fuente', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.fuente_id not in self.partida_ids or not self.fuente_id.partida_empresa_ids:
            raise UserError('Seleccione como fuente una partida con empresas dentro de la selección.')
        require_companies(self, self.partida_ids.sudo().company_ids)
        if len(self.partida_ids.procedimiento_id) != 1:
            raise UserError('Las partidas deben pertenecer al mismo procedimiento.')
        for target in self.partida_ids - self.fuente_id:
            source = self.fuente_id.partida_empresa_ids.sorted(lambda a: (a.sequence, a.id))
            target.write({'partida_empresa_ids': [Command.clear()] + [Command.create({'company_id': a.company_id.id, 'sequence': n * 10}) for n, a in enumerate(source, 1)]})
        return close()


class PropagarProveedores(models.TransientModel):
    _name = 'licitacion.propagar.proveedores.wizard'
    _description = 'Propagar proveedores'

    partida_ids = fields.Many2many('licitacion.partida', string='Partidas seleccionadas', required=True)
    fuente_id = fields.Many2one('licitacion.partida', string='Partida fuente', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.fuente_id not in self.partida_ids or not self.fuente_id.partida_proveedor_ids:
            raise UserError('Seleccione como fuente una partida con proveedores dentro de la selección.')
        if len(self.partida_ids.procedimiento_id) != 1:
            raise UserError('Las partidas deben pertenecer al mismo procedimiento.')
        for target in self.partida_ids - self.fuente_id:
            target.write({'partida_proveedor_ids': [Command.clear()] + [Command.create({'partner_id': a.partner_id.id}) for a in self.fuente_id.partida_proveedor_ids]})
        return close()
