from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class Settings(models.TransientModel):
    _inherit = 'res.config.settings'

    licitaciones_escalamiento_horas = fields.Integer(string='Escalar incidencias después de (horas)', default=24,
        config_parameter='licitaciones_publicas.escalamiento_horas')
    licitaciones_storage_destino = fields.Char(string='Ubicación documental prevista',
        config_parameter='licitaciones_publicas.storage_destino',
        help='Referencia para una futura migración. No cambia el filestore de Odoo.')

    @api.constrains('licitaciones_escalamiento_horas')
    def _check_hours(self):
        if any(r.licitaciones_escalamiento_horas < 1 for r in self):
            raise ValidationError('El plazo de escalamiento debe ser de al menos una hora.')


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    def _lp_retained(self):
        return self.filtered(lambda a: a.res_model in ('licitacion.carga', 'licitacion.documento.version'))

    def unlink(self):
        if self._lp_retained():
            raise UserError('Los archivos originales y sus versiones deben conservarse.')
        return super().unlink()

    def write(self, vals):
        if {'datas', 'raw', 'db_datas', 'store_fname', 'res_id', 'res_model', 'res_field', 'public', 'access_token'} & vals.keys() and self._lp_retained():
            # New uploads initialize attachment contents in create(), not this path.
            raise UserError('No se puede reemplazar o publicar un archivo de evidencia conservado.')
        return super().write(vals)
