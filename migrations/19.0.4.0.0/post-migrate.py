from odoo import api, SUPERUSER_ID
from odoo.addons.licitaciones_publicas.catalog_resolution import aliases


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    entity = env.ref('licitaciones_publicas.entidad_30')
    entity.write({'nombres_alternativos': ', '.join(aliases(
        (entity.nombres_alternativos or '') + ', VERACRUZ, VERACRUZ DE LA LLAVE'))})
