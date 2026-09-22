from pathlib import Path

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import LicitacionCase, excel

LIST_HEADERS = ['Número de procedimiento', 'Nombre', 'Unidad compradora', 'Estatus', 'Tipo de contratación', 'Fecha de junta de aclaraciones']


@tagged('post_install', '-at_install')
class TestImport(LicitacionCase):
    def test_preview_does_not_write_destination(self):
        p = self.procedure()
        carga = self.preview(p)
        self.assertEqual(carga.state, 'previsualizada')
        self.assertFalse(p.partida_ids)
        self.assertEqual(carga.partidas_nuevas, 1)
        carga._confirm()
        self.assertEqual(len(p.partida_ids), 1)
        self.assertEqual(carga.state, 'confirmada')

    def test_same_file_is_idempotent(self):
        p = self.procedure()
        carga = self.preview(p)
        carga._confirm()
        carga._confirm()
        second = self.preview(p)
        self.assertEqual((second.partidas_nuevas, second.partidas_cambios, second.partidas_sin_cambios), (0, 0, 1))
        second._confirm()
        self.assertEqual(len(p.partida_ids), 1)
        self.assertEqual(len(p.aparicion_ids), 2)

    def test_unknown_identifier_requires_assignment(self):
        p = self.procedure()
        carga = self.preview(p, filename='IA-50-GYR-050GYR999-N-999-2026.xlsx')
        self.assertEqual(carga.state, 'pendiente_asignacion')
        self.assertFalse(carga.procedimiento_id)

    def test_blank_optional_description_is_idempotent(self):
        p = self.procedure()
        rows = [[1, 21601, '21601-0028', '', 'Fibra verde', 'PIEZA', 4000]]
        self.preview(p, rows=rows)._confirm()
        second = self.preview(p, rows=rows)
        self.assertEqual((second.partidas_cambios, second.partidas_sin_cambios), (0, 1))

    def test_stale_preview_rejected(self):
        p = self.procedure()
        first = self.preview(p)
        stale = self.preview(p)
        first._confirm()
        with self.assertRaisesRegex(UserError, 'previsualización'):
            stale._confirm()
        self.assertEqual(stale.state, 'previsualizada')

    def test_original_file_and_snapshot_immutable(self):
        p = self.procedure()
        carga = self.preview(p)
        carga._confirm()
        with self.assertRaises(AccessError):
            carga.write({'fecha_snapshot': '2020-01-01'})
        with self.assertRaises(AccessError):
            carga.aparicion_ids.write({'presente': False})

    def test_service_congruence_and_resolution(self):
        p = self.procedure(tipo='ser')
        rows = [[n, 21601, f'21601-{n:04}', 'FIBRA', f'Fibra {n}', 'PIEZA', 10] for n in range(1, 27)]
        carga = self.preview(p, rows=rows, blanks=1)
        carga._confirm()
        self.assertEqual(len(p.partida_ids), 26)
        self.assertEqual(len(p.incidencia_ids), 1)
        incident = p.incidencia_ids
        self.assertEqual(incident.severidad, 'bloqueante')
        self.assertEqual(p.tipo_contratacion_id.code, 'SER')
        with self.assertRaises(ValidationError):
            incident._resolve('resolver', '')
        incident._resolve('resolver', 'La convocatoria corresponde a bienes; validado por el responsable.')
        self.assertEqual(p.tipo_contratacion_id.code, 'ADQ')
        self.assertEqual(incident.state, 'resuelta')

    def test_gone_preserves_assignments(self):
        p = self.procedure()
        rows = [[n, 21601, f'21601-{n:04}', 'FIBRA', f'Fibra {n}', 'PIEZA', 10] for n in (1, 2)]
        self.preview(p, rows=rows)._confirm()
        p.action_pasar_a_analisis()
        gone = p.partida_ids.filtered(lambda r: r.numero == 2)
        self.assign(gone)
        carga = self.preview(p, rows=rows[:1])
        self.assertEqual(carga.partidas_gone, 1)
        carga._confirm()
        self.assertFalse(gone.sigue_apareciendo)
        self.assertEqual(len(gone.partida_empresa_ids), 3)
        again = self.preview(p, rows=rows)
        again._confirm()
        self.assertTrue(gone.sigue_apareciendo)

    def test_older_snapshot_rejected(self):
        p = self.procedure()
        self.preview(p)._confirm()
        with self.assertRaises(UserError):
            self.preview(p, day='2026-09-20')

    def test_listado_117_synthetic_and_unknown_status(self):
        rows = [[f'LA-50-GYR-050GYR032-N-{n}-2026', f'Procedimiento {n}', 'UC nueva', 'Nuevo estatus', 'Adquisiciones', '23/09/2026 09:00'] for n in range(1, 118)]
        def load():
            wizard = self.env['licitacion.carga.wizard'].create({'archivo': excel(rows, LIST_HEADERS), 'archivo_nombre': 'listado_sintetico.xlsx', 'fecha_snapshot': '2026-09-21'})
            action = wizard.action_preview()
            return self.env['licitacion.preview.wizard'].browse(action['res_id']).carga_id
        carga = load()
        self.assertEqual(carga.procedimientos_nuevos, 117)
        self.assertFalse(self.env['licitacion.estatus.portal'].search([('code', '=', 'NUEVO_ESTATUS')]))
        carga._confirm()
        status = self.env['licitacion.estatus.portal'].search([('code', '=', 'NUEVO_ESTATUS')])
        self.assertEqual(status.estado, 'por_revisar')
        self.assertTrue(status.activity_ids)
        second = load()
        self.assertEqual((second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 117))

    def test_discarded_dates_notify_and_allow_manual_criba(self):
        p = self.procedure()
        p._cribar('descartar', self.reason)
        rows = [[p.identificador, p.nombre_publicado, self.unit.name, 'Vigente', 'ADQ', '24/09/2026 10:00']]
        wizard = self.env['licitacion.carga.wizard'].create({'archivo': excel(rows, LIST_HEADERS), 'archivo_nombre': 'listado.xlsx', 'fecha_snapshot': '2026-09-21'})
        action = wizard.action_preview()
        self.env['licitacion.preview.wizard'].browse(action['res_id']).action_confirm()
        self.assertEqual(p.state, 'descartado')
        self.assertTrue(p.reapertura_habilitada)
        p._cribar('reabrir')
        self.assertEqual(p.state, 'detectado')

    def test_client_detail_fixtures_when_supplied(self):
        fixture_dir = Path(__file__).parent / 'fixtures'
        names = [('IA-50-GYR-050GYR032-N-89-2026.xlsx', 50), ('IA-50-GYR-050GYR014-T-168-2026.xlsx', 1), ('IA-50-GYR-050GYR034-N-98-2026.xlsx', 26)]
        if not all((fixture_dir / name).exists() for name, _ in names):
            self.skipTest('Faltan los 3 Excel reales del cliente; los sintéticos no sustituyen esta prueba.')
        from ..models.importer import LicitacionImporter
        for name, count in names:
            reader = LicitacionImporter(self.env, (fixture_dir / name).read_bytes(), name)
            self.assertEqual(len(reader.rows), count)
