from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError, ValidationError

from ..parser import PARTIDA_FIELDS, business_key
from .common import imported, lock, require_companies, modal


class Partida(models.Model):
    _name = 'licitacion.partida'
    _description = 'Renglón de licitación'
    _inherit = ['mail.thread', 'licitacion.retained']
    _rec_name = 'clave_cucop'
    _order = 'procedimiento_id, partida_especifica, numero, id'

    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', required=True, index=True, ondelete='restrict')
    numero = fields.Integer(string='Núm.', required=True)
    partida_especifica = fields.Char(string='Partida específica', required=True)
    clave_cucop = fields.Char(string='Clave CUCoP+', required=True, index=True)
    descripcion_cucop = fields.Text(string='Descripción CUCoP+')
    descripcion_detallada = fields.Text(string='Descripción detallada', required=True)
    unidad_medida = fields.Char(string='Unidad de medida', required=True)
    cantidad = fields.Float(string='Cantidad', required=True)
    cantidad_min = fields.Float(string='Cantidad mínima')
    cantidad_max = fields.Float(string='Cantidad máxima')
    clave_hash = fields.Char(compute='_compute_key', store=True, index=True)
    importada = fields.Boolean(default=False, readonly=True)
    sigue_apareciendo = fields.Boolean(string='Sigue apareciendo', default=True, readonly=True)
    fecha_ya_no_aparece = fields.Date(readonly=True)
    participacion = fields.Selection([('sin_decidir', 'Sin decidir'), ('participamos', 'Participamos'), ('descartada', 'Descartada')],
                                     string='Participación', compute='_compute_participacion', store=True, tracking=True)
    motivo_descarte_id = fields.Many2one('licitacion.motivo.descarte', string='Motivo de descarte', ondelete='restrict', tracking=True)
    nota_descarte = fields.Text(string='Nota de descarte', tracking=True)
    partida_empresa_ids = fields.One2many('licitacion.partida.empresa', 'partida_id', string='Empresas')
    partida_proveedor_ids = fields.One2many('licitacion.partida.proveedor', 'partida_id', string='Proveedores')
    company_ids = fields.Many2many('res.company', compute='_compute_companies', store=True, string='Empresas asignadas')
    empresa_principal_id = fields.Many2one('res.company', string='Principal', compute='_compute_companies', store=True)
    proveedor_sugerido_ids = fields.Many2many('res.partner', compute='_compute_sugeridos', string='Proveedores sugeridos')
    _key_unique = models.Constraint('UNIQUE(procedimiento_id, clave_hash)', 'Ya existe esta terna de partida, clave y descripción.')
    _quantity_positive = models.Constraint('CHECK(cantidad >= 0 AND cantidad_min >= 0 AND cantidad_max >= 0)', 'Las cantidades deben ser no negativas.')

    @api.depends('partida_especifica', 'clave_cucop', 'descripcion_detallada')
    def _compute_key(self):
        for rec in self:
            rec.clave_hash = business_key({k: rec[k] for k in ('partida_especifica', 'clave_cucop', 'descripcion_detallada')})

    @api.depends('partida_empresa_ids.company_id', 'partida_empresa_ids.rol', 'partida_empresa_ids.sequence')
    def _compute_companies(self):
        for rec in self:
            assigned = rec.partida_empresa_ids.sorted(lambda a: (a.sequence, a._origin.id or 2**63))
            rec.company_ids = assigned.company_id
            rec.empresa_principal_id = assigned[:1].company_id

    @api.depends('partida_empresa_ids', 'motivo_descarte_id')
    def _compute_participacion(self):
        for rec in self:
            rec.participacion = 'participamos' if rec.partida_empresa_ids else 'descartada' if rec.motivo_descarte_id else 'sin_decidir'

    @api.depends('partida_especifica')
    def _compute_sugeridos(self):
        for rec in self:
            rec.proveedor_sugerido_ids = self.env['res.partner'].search([
                ('es_proveedor_licitacion', '=', True), ('claves_cucop_ids.code', '=', rec.partida_especifica)])

    @api.constrains('motivo_descarte_id', 'partida_empresa_ids')
    def _check_descarte(self):
        for rec in self:
            if rec.motivo_descarte_id and (rec.partida_empresa_ids or rec.motivo_descarte_id.aplica_a not in ('partida', 'ambos')):
                raise ValidationError('Una partida descartada requiere motivo aplicable y ninguna empresa asignada.')

    @api.constrains('cantidad_min', 'cantidad_max')
    def _check_range(self):
        if any(r.cantidad_min > r.cantidad_max for r in self):
            raise ValidationError('La cantidad mínima no puede superar la máxima.')

    def _check_editable(self):
        self.check_access('write')
        if self.filtered(lambda p: p.procedimiento_id.state in ('detectado', 'descartado', 'no_viable', 'con_fallo')):
            raise UserError('Confirme En análisis antes de editar las partidas de un procedimiento activo.')

    @api.model_create_multi
    def create(self, vals_list):
        if not imported(self.env):
            protected = {'importada', 'clave_hash', 'company_ids', 'empresa_principal_id', 'participacion', 'sigue_apareciendo', 'fecha_ya_no_aparece'}
            if any(protected & vals.keys() for vals in vals_list) or any('default_' + k in self.env.context for k in protected):
                raise AccessError('La trazabilidad y participación de las partidas son automáticas.')
            procedures = self.env['licitacion.procedimiento'].browse([v['procedimiento_id'] for v in vals_list])
            procedures.check_access('write')
            if procedures.filtered(lambda p: p.state in ('detectado', 'descartado', 'no_viable', 'con_fallo')):
                raise UserError('Confirme En análisis antes de añadir partidas manuales.')
        return super().create(vals_list)

    def write(self, vals):
        if 'procedimiento_id' in vals:
            raise AccessError('Una partida no se puede trasladar a otro procedimiento.')
        if {'participacion', 'company_ids', 'empresa_principal_id', 'clave_hash'} & vals.keys():
            raise AccessError('La participación, el rol y la clave se calculan automáticamente.')
        if not imported(self.env):
            self._check_editable()
            if {'importada', 'sigue_apareciendo', 'fecha_ya_no_aparece'} & vals.keys() or (self.filtered('importada') and set(PARTIDA_FIELDS) & vals.keys()):
                raise AccessError('Los datos del portal se actualizan mediante una carga.')
        return super().write(vals)

    def action_reabrir(self):
        self._check_editable()
        self.write({'motivo_descarte_id': False, 'nota_descarte': False})
        for rec in self:
            rec.message_post(body='Se reabrió la decisión de esta partida.')

    def action_propagar_empresas(self):
        return modal(self.env['licitacion.propagar.empresas.wizard'], {'partida_ids': [Command.set(self.ids)]})

    def action_propagar_proveedores(self):
        return modal(self.env['licitacion.propagar.proveedores.wizard'], {'partida_ids': [Command.set(self.ids)]})


class PartidaEmpresa(models.Model):
    _name = 'licitacion.partida.empresa'
    _description = 'Empresa asignada a una partida'
    _order = 'partida_id, sequence, id'
    _rec_name = 'company_id'
    _check_company_auto = True

    partida_id = fields.Many2one('licitacion.partida', string='Partida', required=True, index=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', string='Empresa', required=True, ondelete='restrict', domain="[('id', 'in', context.get('allowed_company_ids', []))]")
    sequence = fields.Integer(string='Orden', default=10)
    rol = fields.Selection([('principal', 'Principal'), ('secundaria', 'Secundaria')], string='Rol', compute='_compute_rol', store=True)
    fecha_asignacion = fields.Datetime(string='Asignada el', default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one('res.users', string='Asignada por', default=lambda s: s.env.user, readonly=True)
    nota = fields.Text(string='Nota')
    _company_unique = models.Constraint('UNIQUE(partida_id, company_id)', 'La empresa ya está asignada a esta partida.')

    @api.depends('partida_id.partida_empresa_ids.sequence', 'partida_id.partida_empresa_ids.company_id')
    def _compute_rol(self):
        for rec in self:
            siblings = rec.partida_id.partida_empresa_ids.sorted(lambda a: (a.sequence, a._origin.id or 2**63))
            rec.rol = 'principal' if siblings and siblings[0] == rec else 'secundaria'

    def _validate_partidas(self, partidas):
        for partida in partidas:
            partida._check_descarte()
        lines = self.env['licitacion.costeo.linea'].search([('partida_id', 'in', partidas.ids)])
        lines._check_recargo_mayor_principal()

    @api.model_create_multi
    def create(self, vals_list):
        partidas = self.env['licitacion.partida'].browse(sorted({v['partida_id'] for v in vals_list}))
        lock(partidas)
        partidas._check_editable()
        require_companies(self, self.env['res.company'].browse([v['company_id'] for v in vals_list]))
        sequences = {p.id: max(p.sudo().partida_empresa_ids.mapped('sequence') or [0]) for p in partidas}
        for vals in vals_list:
            if 'rol' in vals:
                raise AccessError('El rol es automático y no admite selección manual.')
            vals['user_id'] = self.env.uid
            vals['fecha_asignacion'] = fields.Datetime.now()
            sequences[vals['partida_id']] += 10
            vals['sequence'] = sequences[vals['partida_id']]
        records = super().create(vals_list)
        records.partida_id.sudo().partida_empresa_ids._recompute_recordset(['rol'])
        self._validate_partidas(partidas)
        for rec in records:
            rec.partida_id.message_post(body='Empresa asignada: %s.' % rec.company_id.name)
        return records

    def write(self, vals):
        if {'rol', 'partida_id', 'company_id', 'fecha_asignacion', 'user_id'} & vals.keys():
            raise AccessError('Retire y vuelva a asignar la empresa para cambiarla; el rol es automático.')
        partidas = self.partida_id
        lock(partidas)
        partidas._check_editable()
        require_companies(self, partidas.sudo().company_ids)
        result = super().write(vals)
        partidas.sudo().partida_empresa_ids._recompute_recordset(['rol'])
        self._validate_partidas(partidas)
        for partida in partidas:
            partida.message_post(body='Se actualizó el orden o la nota de las empresas asignadas.')
        return result

    def unlink(self):
        partidas = self.partida_id
        lock(partidas)
        partidas._check_editable()
        require_companies(self, partidas.sudo().company_ids)
        for rec in self:
            if self.env['licitacion.costeo.linea'].search_count([('partida_id', '=', rec.partida_id.id), ('company_id', '=', rec.company_id.id)]):
                raise UserError('La asignación tiene costeo. Consérvela para mantener el expediente.')
            rec.partida_id.message_post(body='Empresa retirada: %s. La siguiente empresa pasa a Principal.' % rec.company_id.name)
        result = super().unlink()
        partidas.sudo().partida_empresa_ids._recompute_recordset(['rol'])
        self._validate_partidas(partidas)
        return result


class PartidaProveedor(models.Model):
    _name = 'licitacion.partida.proveedor'
    _description = 'Proveedor asignado a una partida'
    _rec_name = 'partner_id'

    partida_id = fields.Many2one('licitacion.partida', string='Partida', required=True, index=True, ondelete='restrict')
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, ondelete='restrict', domain="[('es_proveedor_licitacion', '=', True)]")
    fecha_asignacion = fields.Datetime(string='Asignado el', default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one('res.users', string='Asignado por', default=lambda s: s.env.user, readonly=True)
    _partner_unique = models.Constraint('UNIQUE(partida_id, partner_id)', 'El proveedor ya está asignado a esta partida.')

    @api.constrains('partner_id', 'partida_id')
    def _check_partner(self):
        for rec in self:
            rec.partner_id.check_access('read')
            if not rec.partner_id.es_proveedor_licitacion or rec.partner_id.company_id:
                raise ValidationError('Seleccione un proveedor de licitaciones compartido entre empresas.')

    @api.model_create_multi
    def create(self, vals_list):
        partidas = self.env['licitacion.partida'].browse([v['partida_id'] for v in vals_list])
        lock(partidas)
        partidas._check_editable()
        for vals in vals_list:
            vals['user_id'] = self.env.uid
            vals['fecha_asignacion'] = fields.Datetime.now()
        records = super().create(vals_list)
        for rec in records:
            rec.partida_id.message_post(body='Proveedor asignado: %s.' % rec.partner_id.display_name)
        return records

    def write(self, vals):
        self.partida_id._check_editable()
        if {'partida_id', 'partner_id', 'fecha_asignacion', 'user_id'} & vals.keys():
            raise AccessError('Retire y vuelva a asignar al proveedor para cambiarlo.')
        result = super().write(vals)
        for rec in self:
            rec.partida_id.message_post(body='Proveedor actualizado: %s.' % rec.partner_id.display_name)
        return result

    def unlink(self):
        lock(self.partida_id)
        self.partida_id._check_editable()
        for rec in self:
            sent = self.env['licitacion.carta.apoyo'].sudo().search_count([
                ('partida_ids', 'in', rec.partida_id.id), ('partner_id', '=', rec.partner_id.id), ('state', '!=', 'borrador')])
            if sent:
                raise UserError('El proveedor ya tiene una carta enviada. Conserve la asignación como evidencia.')
            rec.partida_id.message_post(body='Proveedor retirado: %s.' % rec.partner_id.display_name)
        return super().unlink()
