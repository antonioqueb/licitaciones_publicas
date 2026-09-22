from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import LicitacionCase
from ..models.common import IMPORT_TOKEN


@tagged('post_install', '-at_install')
class TestWorkflows(LicitacionCase):
    def test_identifier_and_state_flow(self):
        procedure = self.procedure()
        self.assertEqual((procedure.tipo_procedimiento, procedure.caracter, procedure.ejercicio), ('IA', 'N', '2026'))
        procedure.action_pasar_a_analisis()
        self.assertEqual(procedure.state, 'analisis')
        with self.assertRaises(UserError):
            procedure.write({'state': 'con_fallo'})

    def test_discard_requires_reason(self):
        procedure = self.procedure()
        with self.assertRaises(ValidationError):
            procedure._cribar('descartar')
        procedure._cribar('descartar', self.reason, 'Fuera de giro')
        self.assertEqual(procedure.state, 'descartado')
        with self.assertRaises(UserError):
            procedure._cribar('reabrir')

    def test_batch_screening(self):
        records = self.env['licitacion.procedimiento']
        for n in range(1, 6):
            records |= self.procedure(n)
        form = self.modal_form(records.action_cribar())
        form.decision = 'descartar'
        form.motivo_id = self.reason
        form.nota = 'Prueba por lote'
        wizard = form.save()
        self.assertTrue(wizard.es_lote)
        wizard.action_apply()
        self.assertEqual(set(records.mapped('state')), {'descartado'})

    def test_no_viable_reopens_manually(self):
        p = self.procedure()
        p._cribar('no_viable', self.reason)
        p._cribar('reabrir')
        self.assertEqual(p.state, 'detectado')
        self.assertTrue(p.activity_ids)

    def test_detected_partidas_are_locked(self):
        p = self.procedure()
        line = self.partida(p)
        with self.assertRaises(UserError):
            self.assign(line)

    def test_assignment_append_promote_reorder(self):
        p = self.procedure()
        p.action_pasar_a_analisis()
        line = self.partida(p)
        a = self.assign(line, self.companies[:1])
        b = self.assign(line, self.companies[1:2])
        c = self.assign(line, self.companies[2:])
        self.assertEqual((a.rol, b.rol, c.rol), ('principal', 'secundaria', 'secundaria'))
        self.assertEqual(line.empresa_principal_id, a.company_id)
        b.write({'sequence': 1})
        self.assertEqual((a.rol, b.rol), ('secundaria', 'principal'))
        b.unlink()
        self.assertEqual(a.rol, 'principal')
        a.unlink()
        self.assertEqual(c.rol, 'principal')
        c.unlink()
        self.assertEqual(line.participacion, 'sin_decidir')

    def test_role_cannot_be_overridden(self):
        p = self.procedure()
        p.action_pasar_a_analisis()
        a = self.assign(self.partida(p), self.companies[:1])
        with self.assertRaises(AccessError):
            a.write({'rol': 'secundaria'})

    def test_propagate_assignments_from_selected_source(self):
        p = self.procedure()
        p.action_pasar_a_analisis()
        source = self.partida(p)
        target = self.partida(p, number=2)
        self.assign(source, self.companies[:2])
        self.env['licitacion.partida.proveedor'].create({'partida_id': source.id, 'partner_id': self.partner.id})
        selected = source | target
        for kind in ('empresas', 'proveedores'):
            with self.subTest(kind=kind):
                action = getattr(selected, 'action_propagar_' + kind)()
                self.assertFalse(action.get('res_id'))
                form = self.modal_form(action)
                self.assertFalse(form.fuente_id)
                with self.assertRaises(AssertionError):
                    form.save()
                form.fuente_id = source
                wizard = form.save()
                self.assertEqual(wizard.partida_ids, selected)
                wizard.action_apply()
        self.assertEqual(target.company_ids, source.company_ids)
        self.assertEqual(target.empresa_principal_id, source.empresa_principal_id)
        self.assertEqual(target.partida_proveedor_ids.partner_id, self.partner)

    def test_partida_discard_and_reopen(self):
        p = self.procedure()
        p.action_pasar_a_analisis()
        line = self.partida(p)
        line.write({'motivo_descarte_id': self.reason.id})
        self.assertEqual(line.participacion, 'descartada')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.assign(line)
        line.action_reabrir()
        self.assertEqual(line.participacion, 'sin_decidir')

    def test_three_expedientes_and_letters_idempotent(self):
        p, line, expedientes = self.full_expedientes()
        self.assertEqual(len(expedientes), 3)
        for exp in expedientes:
            self.assertEqual(exp.partida_ids, line)
            self.assertEqual(len(exp.carta_apoyo_ids), 1)
        wizard = self.env['licitacion.generar.expedientes.wizard'].create({'procedimiento_id': p.id})
        wizard.action_generate()
        self.assertEqual(len(p.expediente_ids), 3)
        self.assertEqual(len(p.expediente_ids.carta_apoyo_ids), 3)
        self.assertEqual(p.state, 'preguntas')

    def test_secondary_suggested_and_principal_change_validated(self):
        p, line, exps = self.full_expedientes()
        principal = exps.filtered(lambda e: e.company_id == line.empresa_principal_id)
        secondary = exps - principal
        cost = self.env['licitacion.costeo.linea'].create({'expediente_id': principal.id, 'partida_id': line.id,
            'costo_unitario': 80, 'precio_unitario': 100})
        other = self.env['licitacion.costeo.linea'].create({'expediente_id': secondary[0].id, 'partida_id': line.id,
            'costo_unitario': 80, 'precio_unitario': 110})
        self.assertGreater(other.recargo_secundaria_pct, cost.margen_pct)
        self.assertEqual((cost.total_costo, cost.total_precio, cost.margen_pct), (800, 1000, 20))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            other.recargo_secundaria_pct = 20
        with self.assertRaises(ValidationError), self.cr.savepoint():
            cost.precio_unitario = 1000

    def test_documents_block_publication_and_version(self):
        p, line, exps = self.full_expedientes()
        exp = exps[0]
        doc = self.env['licitacion.documento'].create({'expediente_id': exp.id, 'tipo': 'propio_otro', 'bloqueante': True})
        exp.action_armar()
        with self.assertRaises(UserError):
            exp.action_listo()
        import base64
        doc.write({'archivo': base64.b64encode(b'first'), 'archivo_nombre': 'test.txt', 'state': 'recibido'})
        doc.write({'archivo': base64.b64encode(b'second')})
        self.assertEqual(len(doc.version_ids), 2)
        exp.action_listo()
        exp.action_publicar()
        self.assertEqual(exp.state, 'publicado')
        with self.assertRaises(UserError):
            doc.version_ids.unlink()

    def test_company_partida_consistency(self):
        p, line, exps = self.full_expedientes()
        other = self.procedure(90)
        other_line = self.partida(other)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env['licitacion.pregunta'].create({'expediente_id': exps[0].id, 'partida_id': other_line.id, 'texto': 'Incorrecta'})

    def test_reminders_not_duplicated(self):
        p = self.procedure()
        p.fecha_junta_aclaraciones = fields.Datetime.now() + timedelta(hours=48)
        p._cron_recordatorio_juntas(72)
        p._cron_recordatorio_juntas(72)
        self.assertEqual(len(p.activity_ids.filtered(lambda a: a.summary == 'Junta en 72 h')), 1)

    def test_no_delete_even_manager(self):
        p = self.procedure()
        with self.assertRaises(UserError):
            p.unlink()
