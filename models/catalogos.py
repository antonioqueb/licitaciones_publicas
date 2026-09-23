from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..catalog_resolution import aliases

MX_STATES = 'ags bc bcs camp coah col chis chih df dgo gto gro hgo jal mex mich mor nay nl oax pue qro q_roo slp sin son tab tamps tlax ver yuc zac'.split()


class Catalogo(models.AbstractModel):
    _name = 'licitacion.catalogo'
    _description = 'Catálogo de licitaciones'
    _inherit = 'licitacion.retained'
    _order = 'code, name'

    name = fields.Char(string='Nombre', required=True, translate=False)
    code = fields.Char(string='Código', required=True, index=True)
    active = fields.Boolean(string='Activo', default=True)
    _code_unique = models.Constraint('UNIQUE(code)', 'El código debe ser único.')


class Entidad(models.Model):
    _name = 'licitacion.entidad.federativa'
    _description = 'Entidad federativa'
    _inherit = 'licitacion.catalogo'
    _rec_name = 'nombre'

    codigo_in = fields.Char(related='code', string='Código INEGI', readonly=True, size=2)
    estado_base_id = fields.Many2one('res.country.state', compute='_compute_estado_base', store=True, readonly=True)
    nombre = fields.Char(related='estado_base_id.name', string='Nombre oficial Odoo', readonly=True)
    nombres_alternativos = fields.Text(string='Nombres alternativos', help='Alias completos separados por coma.')
    activa = fields.Boolean(related='active', string='Activa', readonly=True)
    notas = fields.Text(string='Notas internas', readonly=True)
    procedimiento_count = fields.Integer(compute='_compute_procedimientos', string='Procedimientos')

    @api.depends('code')
    def _compute_estado_base(self):
        for rec in self:
            number = int(rec.code) if (rec.code or '').isdigit() else 0
            rec.estado_base_id = self.env.ref('base.state_mx_' + MX_STATES[number - 1], raise_if_not_found=False) if 1 <= number <= 32 else False

    def _compute_procedimientos(self):
        for rec in self:
            rec.procedimiento_count = self.env['licitacion.procedimiento'].search_count([('entidad_id', '=', rec.id)])

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError('Las 32 entidades se suministran con el módulo. Solo se editan sus alias.')
        for vals in vals_list:
            if 'nombres_alternativos' in vals:
                vals['nombres_alternativos'] = ', '.join(aliases(vals['nombres_alternativos']))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and set(vals) - {'nombres_alternativos'}:
            raise AccessError('Solo se pueden editar los nombres alternativos de una entidad.')
        if 'nombres_alternativos' in vals:
            vals = dict(vals, nombres_alternativos=', '.join(aliases(vals['nombres_alternativos'])))
        return super().write(vals)

    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if rec.code not in {str(n).zfill(2) for n in range(1, 33)}:
                raise ValidationError('El código INEGI debe estar entre 01 y 32.')


class Unidad(models.Model):
    _name = 'licitacion.unidad.compradora'
    _description = 'Unidad compradora'
    _inherit = 'licitacion.catalogo'

    dependencia = fields.Char(string='Dependencia')
    entidad_id = fields.Many2one('licitacion.entidad.federativa', string='Entidad', ondelete='restrict')


class Estatus(models.Model):
    _name = 'licitacion.estatus.portal'
    _description = 'Estatus del portal'
    _inherit = ['licitacion.catalogo', 'mail.thread', 'mail.activity.mixin']

    tipo = fields.Selection([('base', 'Base'), ('auto_creado', 'Creado al importar')], default='base', required=True)
    estado = fields.Selection([('activo', 'Activo'), ('por_revisar', 'Por revisar'), ('inactivo', 'Inactivo')], default='activo', required=True)


class Motivo(models.Model):
    _name = 'licitacion.motivo.descarte'
    _description = 'Motivo de descarte'
    _inherit = 'licitacion.catalogo'

    aplica_a = fields.Selection([('procedimiento', 'Procedimiento'), ('partida', 'Partida'), ('ambos', 'Ambos')], default='ambos', required=True)


class Tipo(models.Model):
    _name = 'licitacion.tipo.contratacion'
    _description = 'Tipo de contratación'
    _inherit = 'licitacion.catalogo'

    clave_identificador = fields.Char(string='Clave del identificador')


class Cucop(models.Model):
    _name = 'licitacion.clave.cucop'
    _description = 'Agrupador CUCoP+'
    _inherit = 'licitacion.catalogo'


class Partner(models.Model):
    _inherit = 'res.partner'

    es_proveedor_licitacion = fields.Boolean(string='Es proveedor de licitaciones')
    claves_cucop_ids = fields.Many2many('licitacion.clave.cucop', string='Claves CUCoP+')
    actividad_licitacion = fields.Char(string='Giro de licitaciones')


class Company(models.Model):
    _inherit = 'res.company'

    firma_representante_legal = fields.Binary(string='Firma del representante legal', attachment=True)
    representante_legal = fields.Char(string='Representante legal')
