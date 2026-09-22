from odoo import api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

# Identity capability cannot be supplied over JSON/RPC. Never use a boolean bypass.
IMPORT_TOKEN = object()
FLOW_TOKEN = object()


def imported(env):
    return env.context.get('_lp_import') is IMPORT_TOKEN


def internal(env):
    return env.context.get('_lp_flow') is FLOW_TOKEN


def lock(records):
    records.check_access('write')
    if records:
        records.flush_recordset()
        records.env.cr.execute(SQL('SELECT id FROM %s WHERE id IN %s ORDER BY id FOR UPDATE',
                                  SQL.identifier(records._table), tuple(sorted(records.ids))))
        records.invalidate_recordset()


def require_companies(records, companies):
    companies.check_access('read')
    if set(companies.ids) - set(records.env.companies.ids):
        raise AccessError('Active todas las empresas seleccionadas antes de continuar.')


def modal(model, values=None):
    rec = model.create(values or {})
    return {'type': 'ir.actions.act_window', 'res_model': model._name,
            'res_id': rec.id, 'view_mode': 'form', 'target': 'new'}


class Retained(models.AbstractModel):
    _name = 'licitacion.retained'
    _description = 'Registro con conservación permanente'

    def unlink(self):
        raise UserError('Este registro conserva evidencia y no se puede borrar. Utilice archivar o una nueva versión.')


class CompanyChild(models.AbstractModel):
    _name = 'licitacion.company.child'
    _description = 'Validación de contenido por expediente'

    def _check_expediente_access(self, expediente_id):
        exp = self.env['licitacion.expediente'].browse(expediente_id)
        exp.check_access('write')
        require_companies(self, exp.company_id)
        return exp

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            exp_id = vals.get('expediente_id') or self.env.context.get('default_expediente_id')
            if exp_id:
                self._check_expediente_access(exp_id)
            if 'company_id' in vals:
                raise AccessError('La empresa se obtiene del expediente.')
        return super().create(vals_list)

    def write(self, vals):
        if 'company_id' in vals or 'expediente_id' in vals:
            raise AccessError('El contenido no se puede trasladar de expediente o empresa.')
        for exp in self.expediente_id:
            self._check_expediente_access(exp.id)
        return super().write(vals)

    def _check_partida_expediente(self):
        for rec in self:
            if rec.partida_id and rec.partida_id not in rec.expediente_id.partida_ids:
                raise UserError('La partida debe pertenecer al expediente y a su empresa.')
