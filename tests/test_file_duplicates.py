import base64
import hashlib
import io
import uuid
import zipfile
from unittest.mock import patch

from odoo import api, Command, sql_db
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger
from psycopg2.errors import SerializationFailure

from ..models.importer import LicitacionImporter
from .common import LicitacionCase, excel
from .test_import import LIST_HEADERS


@tagged('post_install', '-at_install')
class TestFileDuplicates(LicitacionCase):
    def setUp(self):
        super().setUp()
        self.row = [1, 'LA-50-GYR-050GYR032-N-990-2026', 'Texto del portal', 'Prueba DEV-03', 'IMSS',
                    'Vigente', '', '25/09/2026 10:00', 'Invitación', 'ADQ', 'E-2026-990', 'Unidad de prueba', 'Zacatecas']
        self.binary = excel([self.row], LIST_HEADERS)

    def upload(self, binary=None, name='InformaciónPública_export_dev03.xlsx'):
        return self.env['licitacion.carga.wizard'].create({'archivo': binary or self.binary,
            'archivo_nombre': name, 'fecha_snapshot': '2026-09-22'})

    def preview_file(self, wizard):
        action = wizard.action_preview()
        self.assertEqual(action['res_model'], 'licitacion.preview.wizard')
        return wizard.env[action['res_model']].browse(action['res_id']).carga_id

    def confirm_file(self, wizard=None):
        carga = self.preview_file(wizard or self.upload())
        carga._confirm()
        return carga

    def force_form(self, wizard):
        form = self.modal_form(wizard.action_force())
        form.motivo = 'Revisión de la clasificación recibida del portal.'
        form.confirmado = True
        return form.save()

    def force_file(self, wizard):
        action = self.force_form(wizard).action_confirm()
        return self.env['licitacion.preview.wizard'].browse(action['res_id']).carga_id

    def variant(self):
        stream = io.BytesIO(base64.b64decode(self.binary))
        with zipfile.ZipFile(stream, 'a') as archive:
            archive.comment = b'Descarga nueva: mismos datos, binario distinto.'
        return base64.b64encode(stream.getvalue())

    def test_same_binary_blocks_before_parsing_and_creates_no_load(self):
        first = self.confirm_file()
        self.assertEqual(first.binary_sha256, hashlib.sha256(base64.b64decode(self.binary)).hexdigest())
        self.assertTrue(first.fecha_confirmacion)
        self.assertEqual(first.procesado_por_id, self.env.user)
        count = self.env['licitacion.carga'].search_count([])
        wizard = self.upload(name='archivo_renombrado.xlsx')
        with patch.object(type(wizard), '_reader', side_effect=AssertionError('No volver a validar el binario')):
            wizard._onchange_file()
            self.assertEqual(wizard.cargas_previas_ids, first)
            self.assertEqual(wizard.carga_previa_id, first)
            self.assertEqual(wizard.previa_resumen, first.resumen)
            self.assertEqual(wizard.previa_procesada, first.fecha_confirmacion)
            action = wizard.action_preview()
        self.assertEqual(action['res_model'], wizard._name)
        self.assertEqual(self.env['licitacion.carga'].search_count([]), count)
        self.assertEqual(wizard.action_open_existing()['res_id'], first.id)

    def test_multiple_previous_loads_listed_without_creating_another(self):
        first = self.confirm_file()
        second = self.force_file(self.upload())
        second._confirm()
        # Historical duplicates did not have a force marker; preserve them.
        self.env.cr.execute('UPDATE licitacion_carga SET reimportacion_forzada = FALSE, motivo_reimportacion = NULL WHERE id=%s', [second.id])
        second.invalidate_recordset()
        count = self.env['licitacion.carga'].search_count([])
        wizard = self.upload()
        wizard._onchange_file()
        self.assertEqual(set(wizard.cargas_previas_ids.ids), {first.id, second.id})
        wizard.carga_previa_id = first
        self.assertEqual(wizard.action_open_existing()['res_id'], first.id)
        wizard.action_preview()
        self.assertEqual(self.env['licitacion.carga'].search_count([]), count)
        first.invalidate_recordset(['coincidencias_ids', 'coincidencias_count'])
        self.assertEqual(first.coincidencias_count, 2)

    def test_force_requires_reason_and_confirmation_and_is_audited_once(self):
        first = self.confirm_file()
        wizard = self.upload()
        force = self.env['licitacion.forzar.carga.wizard'].create({'carga_wizard_id': wizard.id, 'motivo': ' '})
        for values in ({'confirmado': False, 'motivo': 'Prueba'}, {'confirmado': True, 'motivo': ' '}):
            force.write(values)
            with self.assertRaises(UserError):
                force.action_confirm()
        force.write({'motivo': 'Corregir catálogos revisados por el cliente.', 'confirmado': True})
        action = force.action_confirm()
        second = self.env['licitacion.preview.wizard'].browse(action['res_id']).carga_id
        repeated = force.action_confirm()
        self.assertEqual(self.env['licitacion.preview.wizard'].browse(repeated['res_id']).carga_id, second)
        self.assertNotEqual(first, second)
        self.assertTrue(second.reimportacion_forzada)
        self.assertEqual(second.cargas_origen_ids, first)
        self.assertEqual(len(second.message_ids.filtered(lambda m: 'Corregir catálogos' in (m.body or ''))), 1)
        self.assertEqual((second.procedimientos_nuevos, second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 0, 1))
        second._confirm()
        second._confirm()
        self.assertEqual(len(second.aparicion_ids), 1)
        self.assertEqual(len(second.message_ids.filtered(lambda m: 'Importación confirmada por' in (m.body or ''))), 1)

    def test_different_bytes_can_have_zero_changes(self):
        first = self.confirm_file()
        second = self.preview_file(self.upload(self.variant()))
        self.assertNotEqual(second.binary_sha256, first.binary_sha256)
        self.assertFalse(second.reimportacion_forzada)
        self.assertEqual(second.carga_base_id, first)
        self.assertFalse(second.aviso_base)
        self.assertEqual((second.procedimientos_nuevos, second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 0, 1))
        second._confirm()

    def test_edited_file_with_same_name_is_imported(self):
        first = self.confirm_file()
        self.row[3] = 'Nombre publicado corregido'
        second = self.preview_file(self.upload(excel([self.row], LIST_HEADERS)))
        self.assertNotEqual(second.binary_sha256, first.binary_sha256)
        self.assertEqual(second.procedimientos_cambios, 1)
        second._confirm()
        self.assertEqual(first.aparicion_ids.procedimiento_id.nombre_publicado, self.row[3])

    def test_pending_uploads_do_not_block_but_second_confirmation_does(self):
        first = self.preview_file(self.upload())
        wizard = self.upload()
        self.assertFalse(wizard.cargas_previas_ids)
        second = self.preview_file(wizard)
        first._confirm()
        with self.assertRaisesRegex(UserError, 'ya fue procesado'):
            second._confirm()
        self.assertEqual(second.state, 'previsualizada')

    def test_unassigned_detail_does_not_block_a_second_upload(self):
        from .common import HEADERS
        binary = excel([[1, 21601, '21601-0028', 'Fibra', 'Detalle por asignar', 'PIEZA', 5]], HEADERS)
        name = 'IA-50-GYR-050GYR999-N-999-2026.xlsx'
        first_wizard = self.upload(binary, name)
        first_wizard.action_preview()
        first = first_wizard.carga_id
        self.assertEqual(first.state, 'pendiente_asignacion')
        second_wizard = self.upload(binary, name)
        self.assertFalse(second_wizard.cargas_previas_ids)
        second_wizard.action_preview()
        self.assertNotEqual(first, second_wizard.carga_id)
        self.assertEqual(second_wizard.carga_id.state, 'pendiente_asignacion')

    def test_double_preview_and_double_confirmation_reuse_same_load(self):
        wizard = self.upload()
        first = self.preview_file(wizard)
        second = self.preview_file(wizard)
        self.assertEqual(first, second)
        first._confirm()
        action = wizard.action_preview()
        self.assertEqual((action['res_model'], action['res_id']), ('licitacion.carga', first.id))
        first._confirm()
        self.assertEqual(len(first.aparicion_ids), 1)

    def test_force_confirmation_cannot_be_reused_for_changed_input(self):
        self.confirm_file()
        wizard = self.upload()
        force = self.force_form(wizard)
        wizard.archivo = self.variant()
        with self.assertRaisesRegex(UserError, 'Cambió el archivo'):
            force.action_confirm()
        with self.assertRaises(AccessError):
            force.write({'expected_request': 'forged'})
        with self.assertRaises(AccessError):
            wizard.write({'carga_id': 1})

    def test_rpc_defaults_cannot_forge_force_or_cached_result(self):
        wizard = self.upload().with_context(default_reimportacion_forzada=True,
            default_motivo_reimportacion='Motivo inyectado', default_state='confirmada')
        carga = self.preview_file(wizard)
        self.assertFalse(carga.reimportacion_forzada)
        self.assertFalse(carga.motivo_reimportacion)
        self.assertEqual(carga.state, 'previsualizada')
        model = self.env['licitacion.carga.wizard'].with_context(default_carga_id=carga.id,
            default_request_fingerprint='forged')
        other = model.create({'archivo': self.binary, 'archivo_nombre': wizard.archivo_nombre,
                              'fecha_snapshot': '2026-09-22'})
        self.assertFalse(other.carga_id)
        self.assertFalse(other.request_fingerprint)

    def test_backfill_hash_on_closed_history_keeps_business_fields_unchanged(self):
        first = self.confirm_file()
        before = (first.state, first.resumen, first.user_id, first.create_date, first.write_date, first.aparicion_ids.ids)
        self.env.cr.execute('UPDATE licitacion_carga SET binary_sha256 = NULL WHERE id=%s', [first.id])
        first.invalidate_recordset(['binary_sha256'])
        self.env.add_to_compute(first._fields['binary_sha256'], first)
        first.flush_recordset(['binary_sha256'])
        self.assertEqual(self.upload().cargas_previas_ids, first)
        self.assertEqual((first.state, first.resumen, first.user_id, first.create_date, first.write_date, first.aparicion_ids.ids), before)

    def test_empty_baseline_is_explicit_and_current_procedures_are_not_new(self):
        procedure = self.procedure(number=990)
        self.row[1] = procedure.identificador
        self.binary = excel([self.row], LIST_HEADERS)
        carga = self.preview_file(self.upload())
        self.assertTrue(carga.aviso_base)
        self.assertFalse(carga.carga_base_id)
        self.assertEqual(carga.procedimientos_nuevos, 0)
        carga._confirm()
        with patch.object(LicitacionImporter, '_current', return_value=(self.env['licitacion.procedimiento'], {}, {})):
            with self.assertRaisesRegex(UserError, 'no se usará una comparación vacía'):
                self.preview_file(self.upload(self.variant()))

    def test_hidden_company_history_is_not_disclosed(self):
        company = self.companies[0]
        other = self.companies[1]
        user = new_test_user(self.env, login='dev03_upload', groups='licitaciones_publicas.group_licitaciones_user',
                             company_id=other.id, company_ids=[Command.set(other.ids)])
        wizard = self.upload().with_context(allowed_company_ids=company.ids)
        first = self.confirm_file(wizard)
        limited = self.env['licitacion.carga.wizard'].with_user(user).with_context(allowed_company_ids=other.ids)
        values = {'archivo': self.binary, 'archivo_nombre': 'InformaciónPública_export_dev03.xlsx', 'fecha_snapshot': '2026-09-22'}
        wizard = limited.create(dict(values))
        self.assertEqual(wizard.env.uid, user.id)
        self.assertFalse(wizard.env.su)
        self.assertFalse(wizard.cargas_previas_ids)
        with self.assertRaises(AccessError):
            first.with_env(limited.env).check_access('read')
        with self.assertRaises(AccessError):
            wizard.write({'carga_previa_id': first.id})
        with self.assertRaises(AccessError):
            limited.create(dict(values, carga_previa_id=first.id))
        with self.assertRaises(AccessError):
            limited.with_context(default_carga_previa_id=first.id).create(dict(values))
        with self.assertRaises(AccessError):
            limited.new(dict(values, carga_previa_id=first.id))._onchange_previous()
        self.assertFalse(wizard.carga_previa_id)

    def test_visible_previous_load_can_be_selected_by_normal_user(self):
        company = self.companies[0]
        first = self.confirm_file(self.upload().with_context(allowed_company_ids=company.ids))
        user = new_test_user(self.env, login='dev03_visible', groups='licitaciones_publicas.group_licitaciones_user',
                            company_id=company.id, company_ids=[Command.set(company.ids)])
        limited = self.env['licitacion.carga.wizard'].with_user(user).with_context(allowed_company_ids=company.ids)
        values = {'archivo': self.binary, 'archivo_nombre': 'InformaciónPública_export_dev03.xlsx', 'fecha_snapshot': '2026-09-22'}
        wizard = limited.create(dict(values, carga_previa_id=first.id))
        self.assertEqual(wizard.action_open_existing()['res_id'], first.id)
        wizard.write({'carga_previa_id': False})
        wizard.write({'carga_previa_id': first.id})
        wizard._onchange_previous()
        self.assertEqual(wizard.carga_previa_id, first)
        defaulted = limited.with_context(default_carga_previa_id=first.id).create(dict(values))
        self.assertEqual(defaulted.carga_previa_id, first)
        with self.assertRaises(ValidationError):
            wizard.write({'archivo': self.variant()})
        with self.assertRaises(ValidationError):
            limited.create(dict(values, archivo=self.variant(), carga_previa_id=first.id))

    def test_catalog_duplicate_requires_explicit_force(self):
        headers = ['Partida específica', 'Clave CUCoP+', 'Descripción SAI', 'Descripción CUCoP+'] + [f'Extra {i}' for i in range(6)]
        binary = excel([[29999, '29999-0001', 'SAI de prueba', 'Fibra'] + [''] * 6], headers)
        first = self.confirm_file(self.upload(binary, 'Libro1.xlsx'))
        wizard = self.upload(binary, 'Libro1.xlsx')
        self.assertEqual(wizard.cargas_previas_ids, first)
        self.assertEqual(wizard.action_preview()['res_model'], wizard._name)
        second = self.force_file(wizard)
        second._confirm()
        self.assertTrue(second.reimportacion_forzada)

    def test_transaction_guard_rejects_stale_repeatable_read_snapshot(self):
        # Independent PostgreSQL transactions; no business data is committed.
        sha = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        database = sql_db.db_connect(self.env.cr.dbname)
        try:
            # registry.cursor() is wrapped by TransactionCase, so obtain real
            # connections for this concurrency check (only a random guard row).
            with database.cursor() as first, database.cursor() as stale:
                first_env = api.Environment(first, self.env.uid, {})
                stale_env = api.Environment(stale, self.env.uid, {})
                stale.execute('SELECT count(*) FROM licitacion_archivo_huella')
                first_env['licitacion.archivo.huella']._serialize(sha)
                first.commit()
                with mute_logger('odoo.sql_db'), self.assertRaises(SerializationFailure):
                    stale_env['licitacion.archivo.huella']._serialize(sha)
                stale.rollback()
                stale_env['licitacion.archivo.huella']._serialize(sha)
                stale.rollback()
        finally:
            with database.cursor() as cleanup:
                cleanup.execute('DELETE FROM licitacion_archivo_huella WHERE binary_sha256=%s', [sha])
                cleanup.commit()
