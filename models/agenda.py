from odoo import fields, models, tools


class FechaFatal(models.Model):
    _name = 'licitacion.fecha.fatal'
    _description = 'Fecha fatal de procedimiento'
    _auto = False
    _order = 'fecha, procedimiento_id'
    _rec_name = 'name'

    name = fields.Char(string='Procedimiento', readonly=True)
    procedimiento_id = fields.Many2one('licitacion.procedimiento', string='Procedimiento', readonly=True)
    tipo = fields.Selection([('junta', 'Junta de aclaraciones'), ('preguntas', 'Límite de preguntas'),
                             ('muestras', 'Entrega de muestras'), ('apertura', 'Apertura'), ('fallo', 'Fallo')], string='Evento', readonly=True)
    fecha = fields.Datetime(string='Fecha y hora', readonly=True)
    state = fields.Selection(related='procedimiento_id.state', string='Estado interno')
    tipo_contratacion_id = fields.Many2one(related='procedimiento_id.tipo_contratacion_id')
    user_id = fields.Many2one(related='procedimiento_id.user_id', string='Responsable')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE VIEW licitacion_fecha_fatal AS
            SELECT p.id * 10 + v.n AS id, p.id AS procedimiento_id,
                   p.identificador AS name, v.tipo, v.fecha
            FROM licitacion_procedimiento p
            CROSS JOIN LATERAL (VALUES
                (1, 'junta', p.fecha_junta_aclaraciones),
                (2, 'preguntas', p.fecha_limite_preguntas),
                (3, 'muestras', p.fecha_entrega_muestras),
                (4, 'apertura', p.fecha_apertura),
                (5, 'fallo', p.fecha_fallo)
            ) AS v(n, tipo, fecha)
            WHERE v.fecha IS NOT NULL AND p.active
        ''')

    def action_open_procedimiento(self):
        self.ensure_one()
        self.procedimiento_id.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': 'licitacion.procedimiento',
                'res_id': self.procedimiento_id.id, 'view_mode': 'form'}
