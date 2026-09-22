from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import LicitacionCase


@tagged('post_install', '-at_install')
class TestSecurity(LicitacionCase):
    def restricted_user(self):
        return self.env['res.users'].create({'name': 'Usuario restringido de prueba', 'login': 'lp_test_user',
            'company_id': self.companies[0].id, 'company_ids': [Command.set(self.companies[:1].ids)],
            'group_ids': [Command.set([self.env.ref('licitaciones_publicas.group_licitaciones_user').id])]})

    def test_expedientes_and_children_company_isolation(self):
        p, line, expedientes = self.full_expedientes()
        user = self.restricted_user()
        records = self.env['licitacion.expediente'].with_user(user).with_context(allowed_company_ids=self.companies[:1].ids)
        visible = records.search([('procedimiento_id', '=', p.id)])
        self.assertEqual(visible.company_id, self.companies[0])
        forbidden = expedientes.filtered(lambda e: e.company_id == self.companies[1])
        with self.assertRaises(AccessError):
            records.browse(forbidden.id).read(['folio'])
        cartas = self.env['licitacion.carta.apoyo'].with_user(user).with_context(allowed_company_ids=self.companies[:1].ids)
        self.assertEqual(len(cartas.search([('expediente_id', 'in', expedientes.ids)])), 1)

    def test_import_bypass_not_forgeable(self):
        p = self.procedure()
        with self.assertRaises(AccessError):
            p.with_context(_lp_import=True).write({'estatus_portal_id': self.env.ref('licitaciones_publicas.estatus_vigente').id})
        with self.assertRaises(UserError):
            p.with_context(_lp_flow=True).write({'state': 'analisis'})

    def test_cannot_assign_unauthorized_company(self):
        p = self.procedure()
        p.action_pasar_a_analisis()
        line = self.partida(p)
        user = self.restricted_user()
        model = self.env['licitacion.partida.empresa'].with_user(user).with_context(allowed_company_ids=self.companies[:1].ids)
        with self.assertRaises(AccessError):
            model.create({'partida_id': line.id, 'company_id': self.companies[1].id})

    def test_normal_user_cannot_change_catalog(self):
        user = self.restricted_user()
        with self.assertRaises(AccessError):
            self.reason.with_user(user).write({'name': 'No autorizado'})
