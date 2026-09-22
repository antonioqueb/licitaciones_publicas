from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
