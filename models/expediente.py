import base64
import math
import random

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .common import FLOW_TOKEN, internal, lock, require_companies

DOCUMENT_TYPES = [
    ('prov_ficha', 'Ficha técnica'), ('prov_certificado', 'Certificado de calidad'),
    ('prov_registro_cofepris', 'Registro sanitario COFEPRIS'), ('prov_msds', 'Hoja de datos de seguridad'),
    ('prov_composicion', 'Certificado de composición / origen'), ('prov_respaldo_imss', 'Carta de respaldo de abasto IMSS'),
    ('prov_muestra', 'Muestra física'), ('propio_pago_bases', 'Pago de bases'),
    ('propio_fianza_sostenimiento', 'Fianza de sostenimiento'), ('propio_fianza_cumplimiento', 'Fianza de cumplimiento'),
    ('propio_acta_constitutiva', 'Acta constitutiva'), ('propio_poder_legal', 'Poder notarial'),
    ('propio_opinion_sat', 'Opinión positiva SAT'), ('propio_opinion_imss', 'Opinión positiva IMSS'),
    ('propio_declaracion_integridad', 'Declaración de integridad'), ('propio_otro', 'Otro documento propio'),
]


class Expediente(models.Model):
    _name = 'licitacion.expediente'
    _description = 'Expediente de participación por empresa'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'licitacion.retained']
    _check_company_auto = True
    _order = 'procedimiento_id, company_id'
    _rec_name = 'folio'

    folio = fields.Char(string='Folio', default='/', readonly=True, copy=False)
    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', required=True, tracking=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda s: s.env.company, tracking=True)
    active = fields.Boolean(string='Activo', default=True)
    partida_ids = fields.Many2many('licitacion.partida', compute='_compute_partidas', store=True, string='Partidas')
    proveedor_ids = fields.Many2many('res.partner', compute='_compute_proveedores', store=True, string='Proveedores')
    pregunta_ids = fields.One2many('licitacion.pregunta', 'expediente_id', string='Preguntas')
    costeo_linea_ids = fields.One2many('licitacion.costeo.linea', 'expediente_id', string='Costeo')
    carta_apoyo_ids = fields.One2many('licitacion.carta.apoyo', 'expediente_id', string='Cartas de apoyo')
    documento_ids = fields.One2many('licitacion.documento', 'expediente_id', string='Documentos')
    documento_proveedor_ids = fields.One2many('licitacion.documento', 'expediente_id', domain=[('origen', '=', 'proveedor')], string='Documentos de proveedores')
    documento_propio_ids = fields.One2many('licitacion.documento', 'expediente_id', domain=[('origen', '=', 'propio')], string='Documentos propios')
    partidas_count = fields.Integer(compute='_compute_counts', string='Partidas')
    proveedores_count = fields.Integer(compute='_compute_counts', string='Proveedores')
    preguntas_count = fields.Integer(compute='_compute_counts', string='Preguntas')
    total_costo = fields.Monetary(compute='_compute_totales', store=True, string='Costo total')
    total_precio = fields.Monetary(compute='_compute_totales', store=True, string='Precio total')
    margen_bruto = fields.Monetary(compute='_compute_totales', store=True, string='Margen bruto')
    margen_pct = fields.Float(compute='_compute_totales', store=True, string='Margen %')
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    bloqueantes_pendientes = fields.Text(compute='_compute_bloqueantes', string='Bloqueantes pendientes')
    state = fields.Selection([('borrador', 'Borrador'), ('en_armado', 'En armado'), ('listo', 'Listo para publicar'), ('publicado', 'Publicado')], string='Estado', default='borrador', required=True, tracking=True)
    _company_unique = models.Constraint('UNIQUE(procedimiento_id, company_id)', 'Ya existe un expediente para esta empresa y procedimiento.')

    @api.depends('procedimiento_id.partida_ids.partida_empresa_ids.company_id', 'company_id')
    def _compute_partidas(self):
        for rec in self:
            rec.partida_ids = rec.procedimiento_id.partida_ids.filtered(lambda p: rec.company_id in p.company_ids)

    @api.depends('partida_ids.partida_proveedor_ids.partner_id')
    def _compute_proveedores(self):
        for rec in self:
            rec.proveedor_ids = rec.partida_ids.partida_proveedor_ids.partner_id

    @api.depends('partida_ids', 'proveedor_ids', 'pregunta_ids')
    def _compute_counts(self):
        for rec in self:
            rec.partidas_count, rec.proveedores_count, rec.preguntas_count = len(rec.partida_ids), len(rec.proveedor_ids), len(rec.pregunta_ids)

    @api.depends('costeo_linea_ids.total_costo', 'costeo_linea_ids.total_precio')
    def _compute_totales(self):
        for rec in self:
            rec.total_costo = sum(rec.costeo_linea_ids.mapped('total_costo'))
            rec.total_precio = sum(rec.costeo_linea_ids.mapped('total_precio'))
            rec.margen_bruto = rec.total_precio - rec.total_costo
            rec.margen_pct = rec.margen_bruto / rec.total_precio * 100 if rec.total_precio else 0

    @api.depends('documento_ids.bloqueante', 'documento_ids.state', 'documento_ids.fecha_vencimiento',
                 'procedimiento_id.incidencia_ids.state')
    def _compute_bloqueantes(self):
        today = fields.Date.context_today(self)
        for rec in self:
            pending = rec.documento_ids.filtered(lambda d: d.bloqueante and d.state != 'no_aplica' and (
                d.state != 'recibido' or (d.fecha_vencimiento and d.fecha_vencimiento < today)))
            labels = [dict(DOCUMENT_TYPES)[d.tipo] for d in pending]
            if rec.procedimiento_id.incidencia_ids.filtered(lambda i: i.state == 'abierta' and i.severidad == 'bloqueante'):
                labels.append('Incidencias bloqueantes abiertas')
            rec.bloqueantes_pendientes = '\n'.join(labels)

    @api.model_create_multi
    def create(self, vals_list):
        require_companies(self, self.env['res.company'].browse([v.get('company_id', self.env.company.id) for v in vals_list]))
        for vals in vals_list:
            procedure = self.env['licitacion.procedimiento'].browse(vals['procedimiento_id'])
            procedure.check_access('write')
            if vals.get('company_id', self.env.company.id) not in procedure.company_ids.ids:
                raise ValidationError('La empresa debe estar asignada a una partida del procedimiento.')
            if vals.get('state', 'borrador') != 'borrador':
                raise ValidationError('El expediente comienza como Borrador.')
            vals.setdefault('state', 'borrador')
            vals['folio'] = self.env['ir.sequence'].next_by_code('licitacion.expediente') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if {'company_id', 'procedimiento_id', 'folio'} & vals.keys():
            raise UserError('La identidad de un expediente es permanente.')
        if 'state' in vals and not internal(self.env):
            raise UserError('Utilice las acciones del expediente para cambiar de etapa.')
        return super().write(vals)

    def action_armar(self):
        if any(r.state != 'borrador' for r in self):
            raise UserError('Solo un borrador puede pasar a En armado.')
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'en_armado'})

    def action_listo(self):
        lock(self)
        if any(r.state != 'en_armado' or r.bloqueantes_pendientes for r in self):
            raise UserError('Complete los bloqueantes de un expediente En armado.')
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'listo'})

    def action_publicar(self):
        lock(self)
        self._compute_bloqueantes()
        if any(r.state != 'listo' or r.bloqueantes_pendientes for r in self):
            raise UserError('La propuesta requiere expediente Listo y ningún bloqueante pendiente.')
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'publicado'})

    def action_print_cartas_zip(self):
        self.check_access('read')
        if not self.carta_apoyo_ids:
            raise UserError('No hay cartas de apoyo en los expedientes seleccionados.')
        # Revalidate every company at download time; never attach a multi-company
        # archive to just one expediente, whose readers could see other companies.
        return {'type': 'ir.actions.act_url', 'url': '/licitaciones/cartas.zip?ids=' + ','.join(map(str, self.ids)), 'target': 'self'}


class Pregunta(models.Model):
    _name = 'licitacion.pregunta'
    _description = 'Pregunta para junta de aclaraciones'
    _inherit = ['mail.thread', 'licitacion.retained', 'licitacion.company.child']
    _check_company_auto = True
    _order = 'expediente_id, sequence, id'
    _rec_name = 'texto'

    expediente_id = fields.Many2one('licitacion.expediente', string='Expediente', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='expediente_id.company_id', store=True, index=True)
    sequence = fields.Integer(string='Orden', default=10)
    partida_id = fields.Many2one('licitacion.partida', string='Partida', ondelete='restrict')
    texto = fields.Text(string='Pregunta', required=True, tracking=True)
    autor_id = fields.Many2one('res.users', string='Autor', default=lambda s: s.env.user)
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)
    state = fields.Selection([('borrador', 'Borrador'), ('revision_legal', 'En revisión legal'), ('lista', 'Lista para enviar'), ('enviada', 'Enviada'), ('respondida', 'Respondida')], string='Estado', default='borrador', tracking=True, required=True)
    respuesta_portal = fields.Text(string='Respuesta oficial')
    active = fields.Boolean(default=True, string='Activo')

    @api.constrains('partida_id', 'expediente_id')
    def _check_relations(self):
        self._check_partida_expediente()


class Costeo(models.Model):
    _name = 'licitacion.costeo.linea'
    _description = 'Línea de costeo por empresa'
    _inherit = ['licitacion.retained', 'licitacion.company.child']
    _check_company_auto = True
    _order = 'expediente_id, partida_id'

    expediente_id = fields.Many2one('licitacion.expediente', string='Expediente', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='expediente_id.company_id', store=True, index=True)
    partida_id = fields.Many2one('licitacion.partida', string='Partida', required=True, ondelete='restrict')
    proveedor_id = fields.Many2one('res.partner', string='Proveedor', check_company=True, domain="[('es_proveedor_licitacion', '=', True)]")
    cantidad = fields.Float(related='partida_id.cantidad', string='Cantidad')
    costo_unitario = fields.Monetary(string='Costo unitario', required=True)
    precio_unitario = fields.Monetary(string='Precio unitario', required=True)
    total_costo = fields.Monetary(compute='_compute_totales', store=True, string='Costo total')
    total_precio = fields.Monetary(compute='_compute_totales', store=True, string='Precio total')
    margen_pct = fields.Float(compute='_compute_totales', store=True, string='Margen %')
    recargo_secundaria_pct = fields.Float(string='Recargo secundaria %')
    es_secundaria = fields.Boolean(compute='_compute_secundaria', string='Secundaria')
    currency_id = fields.Many2one(related='expediente_id.currency_id', store=True)
    _partida_unique = models.Constraint('UNIQUE(expediente_id, partida_id)', 'La partida ya tiene costeo en este expediente.')
    _positive = models.Constraint('CHECK(costo_unitario >= 0 AND precio_unitario >= 0)', 'Costo y precio deben ser no negativos.')

    @api.depends('partida_id.empresa_principal_id', 'company_id')
    def _compute_secundaria(self):
        for rec in self:
            rec.es_secundaria = bool(rec.partida_id.empresa_principal_id and rec.company_id != rec.partida_id.empresa_principal_id)

    @api.depends('cantidad', 'costo_unitario', 'precio_unitario')
    def _compute_totales(self):
        for rec in self:
            rec.total_costo = rec.cantidad * rec.costo_unitario
            rec.total_precio = rec.cantidad * rec.precio_unitario
            rec.margen_pct = (rec.precio_unitario - rec.costo_unitario) / rec.precio_unitario * 100 if rec.precio_unitario else 0

    def _principal(self):
        self.ensure_one()
        company = self.partida_id.empresa_principal_id
        require_companies(self, company)
        return self.search([('partida_id', '=', self.partida_id.id), ('company_id', '=', company.id)], limit=1)

    @api.onchange('partida_id', 'expediente_id')
    def _suggest_recargo(self):
        for rec in self:
            if rec.es_secundaria:
                principal = rec._principal()
                if principal:
                    rec.recargo_secundaria_pct = round(principal.margen_pct + random.uniform(5, 15), 2)

    @api.constrains('partida_id', 'expediente_id', 'proveedor_id', 'recargo_secundaria_pct', 'costo_unitario', 'precio_unitario')
    def _check_recargo_mayor_principal(self):
        self._check_partida_expediente()
        for rec in self:
            if not all(math.isfinite(rec[k]) for k in ('costo_unitario', 'precio_unitario', 'recargo_secundaria_pct')):
                raise ValidationError('Los importes y porcentajes deben ser números finitos.')
            if rec.proveedor_id and rec.proveedor_id not in rec.partida_id.partida_proveedor_ids.partner_id:
                raise ValidationError('El proveedor debe estar asignado a esta partida.')
            require_companies(self, rec.partida_id.sudo().company_ids)
            principal = rec._principal()
            siblings = self.search([('partida_id', '=', rec.partida_id.id)])
            for secondary in siblings.filtered('es_secundaria'):
                if not principal:
                    raise ValidationError('Capture primero el costeo de la empresa principal.')
                if secondary.recargo_secundaria_pct <= principal.margen_pct:
                    raise ValidationError('El recargo secundario debe superar el margen de la principal (%.2f%%).' % principal.margen_pct)

    @api.model_create_multi
    def create(self, vals_list):
        partidas = self.env['licitacion.partida'].browse([v['partida_id'] for v in vals_list])
        lock(partidas)
        for vals in vals_list:
            exp = self.env['licitacion.expediente'].browse(vals['expediente_id'])
            partida = self.env['licitacion.partida'].browse(vals['partida_id'])
            require_companies(self, partida.sudo().company_ids)
            if exp.company_id != partida.empresa_principal_id and not vals.get('recargo_secundaria_pct'):
                principal = self.search([('partida_id', '=', partida.id), ('company_id', '=', partida.empresa_principal_id.id)], limit=1)
                if not principal:
                    raise ValidationError('Capture primero el costeo de la empresa principal.')
                vals['recargo_secundaria_pct'] = round(principal.margen_pct + random.uniform(5, 15), 2)
        return super().create(vals_list)

    def write(self, vals):
        lock(self.partida_id)
        return super().write(vals)


class Documento(models.Model):
    _name = 'licitacion.documento'
    _description = 'Documento del expediente'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'licitacion.retained', 'licitacion.company.child']
    _check_company_auto = True
    _rec_name = 'tipo'

    expediente_id = fields.Many2one('licitacion.expediente', string='Expediente', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='expediente_id.company_id', store=True, index=True)
    tipo = fields.Selection(DOCUMENT_TYPES, string='Tipo', required=True, tracking=True)
    origen = fields.Selection([('proveedor', 'Proveedor'), ('propio', 'Empresa licitante')], string='Origen', compute='_compute_origen', store=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', check_company=True)
    partida_id = fields.Many2one('licitacion.partida', string='Partida', ondelete='restrict')
    state = fields.Selection([('pendiente', 'Pendiente'), ('en_gestion', 'En gestión'), ('recibido', 'Recibido'), ('vencido', 'Vencido'), ('no_aplica', 'No aplica')], string='Estado', default='pendiente', required=True, tracking=True)
    fecha_recepcion = fields.Date(string='Recepción', tracking=True)
    fecha_vencimiento = fields.Date(string='Vencimiento', tracking=True)
    monto = fields.Monetary(string='Monto')
    currency_id = fields.Many2one(related='expediente_id.currency_id')
    archivo = fields.Binary(string='Archivo', attachment=True)
    archivo_nombre = fields.Char(string='Nombre del archivo')
    nota = fields.Text(string='Nota')
    bloqueante = fields.Boolean(string='Bloqueante', default=False, tracking=True)
    version_ids = fields.One2many('licitacion.documento.version', 'documento_id', string='Versiones conservadas')
    vencimiento_notificado = fields.Date(readonly=True, copy=False)

    @api.depends('tipo')
    def _compute_origen(self):
        for rec in self:
            rec.origen = 'proveedor' if (rec.tipo or '').startswith('prov_') else 'propio'

    @api.constrains('partida_id', 'expediente_id', 'partner_id', 'tipo', 'state', 'archivo', 'archivo_nombre')
    def _check_documento(self):
        self._check_partida_expediente()
        for rec in self:
            if rec.origen == 'proveedor' and rec.partner_id not in rec.expediente_id.proveedor_ids:
                raise ValidationError('Seleccione un proveedor del expediente.')
            if rec.origen == 'propio' and rec.partner_id:
                raise ValidationError('Los documentos propios no llevan proveedor.')
            content = rec.with_context(bin_size=False).archivo
            if rec.tipo.startswith('propio_fianza') and content:
                if not (rec.archivo_nombre or '').lower().endswith('.pdf') or not base64.b64decode(content).startswith(b'%PDF-'):
                    raise ValidationError('Las fianzas se reciben únicamente como PDF manual.')
            if rec.state == 'recibido' and rec.tipo != 'prov_muestra' and not rec.archivo:
                raise ValidationError('Adjunte el archivo antes de marcarlo como Recibido.')

    def _version(self):
        if self.filtered('archivo') and self.env['ir.attachment']._storage() != 'file':
            raise UserError('Los documentos requieren ir_attachment.location=file y un filestore persistente.')
        for rec in self.with_context(bin_size=False).filtered('archivo'):
            self.env['licitacion.documento.version'].with_context(_lp_flow=FLOW_TOKEN).create({
                'documento_id': rec.id, 'archivo': rec.archivo,
                'archivo_nombre': rec.archivo_nombre or 'Documento', 'user_id': self.env.uid})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._version()
        return records

    def write(self, vals):
        lock(self.expediente_id)
        if 'expediente_id' in vals:
            raise UserError('Un documento no se puede trasladar a otro expediente.')
        result = super().write(vals)
        if vals.get('archivo'):
            self._version()
        return result

    def _cron_vencimientos(self):
        today = fields.Date.context_today(self)
        for rec in self.search([('fecha_vencimiento', '<', today), ('state', 'in', ['recibido', 'vencido'])]):
            rec = rec.with_company(rec.company_id)
            lock(rec.expediente_id)
            if rec.vencimiento_notificado == rec.fecha_vencimiento:
                continue
            rec.write({'state': 'vencido', 'vencimiento_notificado': rec.fecha_vencimiento})
            rec.activity_schedule('mail.mail_activity_data_todo', user_id=rec.expediente_id.procedimiento_id.user_id.id, summary='Renovar documento vencido')


class DocumentoVersion(models.Model):
    _name = 'licitacion.documento.version'
    _description = 'Versión conservada de documento'
    _inherit = 'licitacion.retained'
    _order = 'id desc'
    _rec_name = 'archivo_nombre'

    documento_id = fields.Many2one('licitacion.documento', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='documento_id.company_id', store=True, index=True)
    archivo = fields.Binary(string='Archivo', attachment=True, required=True)
    archivo_nombre = fields.Char(string='Nombre', required=True)
    user_id = fields.Many2one('res.users', string='Autor', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not internal(self.env):
            raise AccessError('Las versiones se crean al adjuntar un documento.')
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError('Las versiones documentales son inmutables.')


class Carta(models.Model):
    _name = 'licitacion.carta.apoyo'
    _description = 'Carta de solicitud de apoyo a proveedor'
    _inherit = ['mail.thread', 'licitacion.retained', 'licitacion.company.child']
    _check_company_auto = True
    _rec_name = 'folio'

    folio = fields.Char(string='Folio', readonly=True, copy=False, default='/')
    expediente_id = fields.Many2one('licitacion.expediente', string='Expediente', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='expediente_id.company_id', store=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, check_company=True, ondelete='restrict')
    partida_ids = fields.Many2many('licitacion.partida', compute='_compute_partidas', store=True, string='Partidas apoyadas')
    state = fields.Selection([('borrador', 'Borrador'), ('enviada', 'Enviada'), ('respondida', 'Respondida')], string='Estado', default='borrador', tracking=True, required=True)
    fecha_envio = fields.Datetime(string='Fecha de envío', readonly=True, tracking=True)
    fecha_respuesta = fields.Datetime(string='Fecha de respuesta', readonly=True, tracking=True)
    _partner_unique = models.Constraint('UNIQUE(expediente_id, partner_id)', 'Ya existe una carta para este proveedor y expediente.')

    @api.depends('expediente_id.partida_ids.partida_proveedor_ids.partner_id', 'partner_id')
    def _compute_partidas(self):
        for rec in self:
            rec.partida_ids = rec.expediente_id.partida_ids.filtered(lambda p: rec.partner_id in p.partida_proveedor_ids.partner_id)

    @api.constrains('expediente_id', 'partner_id')
    def _check_partner(self):
        for rec in self:
            if rec.partner_id not in rec.expediente_id.proveedor_ids:
                raise ValidationError('El proveedor debe apoyar al menos una partida del expediente.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'borrador') != 'borrador':
                raise ValidationError('La carta comienza como Borrador.')
            vals.update(state='borrador', fecha_envio=False, fecha_respuesta=False)
            vals['folio'] = self.env['ir.sequence'].next_by_code('licitacion.carta.apoyo') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if {'folio', 'expediente_id', 'partner_id'} & vals.keys():
            raise UserError('La identidad de una carta es permanente.')
        if {'state', 'fecha_envio', 'fecha_respuesta'} & vals.keys() and not internal(self.env):
            raise UserError('Utilice Enviar o Registrar respuesta.')
        return super().write(vals)

    def action_print_carta(self):
        return self.env.ref('licitaciones_publicas.report_carta_apoyo').report_action(self)

    def action_enviar(self):
        lock(self)
        for rec in self:
            if rec.state != 'borrador' or not rec.partner_id.email:
                raise UserError('Se requiere una carta en Borrador y correo del proveedor.')
            if not rec.partida_ids:
                raise UserError('La carta no tiene partidas apoyadas.')
            self.env.ref('licitaciones_publicas.mail_template_carta_apoyo').send_mail(rec.id, force_send=False)
            rec.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'enviada', 'fecha_envio': fields.Datetime.now()})
            rec.message_post(body='La carta se colocó en la cola de correo para el proveedor.')

    def action_respondida(self):
        if any(r.state != 'enviada' for r in self):
            raise UserError('Solo una carta enviada puede marcarse como Respondida.')
        self.with_context(_lp_flow=FLOW_TOKEN).write({'state': 'respondida', 'fecha_respuesta': fields.Datetime.now()})
