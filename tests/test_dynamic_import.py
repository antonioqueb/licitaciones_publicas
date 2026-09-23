from psycopg2.errors import UniqueViolation

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import LicitacionCase, excel, HEADERS
from .test_import import LIST_HEADERS
from . import test_security as security_tests


@tagged('post_install', '-at_install')
class TestDynamicImport(LicitacionCase):
    def load(self, rows, headers=LIST_HEADERS, filename='InformaciónPública_export_prueba.xlsx'):
        wizard = self.env['licitacion.carga.wizard'].create({
            'archivo': excel(rows, headers), 'archivo_nombre': filename, 'fecha_snapshot': '2026-09-22'})
        action = wizard.action_preview()
        return self.env['licitacion.preview.wizard'].browse(action['res_id']).carga_id

    def list_row(self, identifier):
        return [1, identifier, 'Texto publicado por el portal', 'Procedimiento de prueba', 'IMSS',
                'Vigente', '23/09/2026 10:00', '25/09/2026 10:00', 'Invitación', 'ADQ',
                'E-2026-00101658', 'UC de prueba', 'Zacatecas']

    def test_official_headers_preserve_all_columns_and_remain_idempotent(self):
        row = self.list_row('LA-50-GYR-050GYR032-N-990-2026')
        carga = self.load([row])
        self.assertFalse(carga.aparicion_ids)
        self.assertFalse(self.env['licitacion.procedimiento'].search([('identificador', '=', row[1])]))
        carga._confirm()
        p = carga.aparicion_ids.procedimiento_id
        self.assertEqual(p.numero_listado, 1)
        self.assertEqual(p.caracter_publicado, row[2])
        self.assertEqual(p.siglas_dependencia, 'IMSS')
        self.assertEqual(p.tipo_publicacion, 'Invitación')
        self.assertEqual(p.codigo_expediente, 'E-2026-00101658')
        self.assertEqual(p.fecha_junta_aclaraciones, fields.Datetime.to_datetime('2026-09-23 16:00:00'))
        self.assertEqual(p.fecha_apertura, fields.Datetime.to_datetime('2026-09-25 16:00:00'))
        self.assertEqual(p.caracter_procedimiento_id.descripcion, 'Por definir por cliente')
        self.assertEqual(carga.aparicion_ids.datos_snapshot['caracter_publicado'], row[2])
        second = self.load([row])
        self.assertEqual((second.procedimientos_nuevos, second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 0, 1))
        second._confirm()
        with self.assertRaises(AccessError):
            p.write({'caracter_publicado': 'Edición manual'})

    def test_official_listing_accepts_empty_junta(self):
        row = self.list_row('LA-50-GYR-050GYR032-N-990-2026')
        row[6] = ''
        carga = self.load([row])
        carga._confirm()
        self.assertFalse(carga.aparicion_ids.procedimiento_id.fecha_junta_aclaraciones)
        self.assertTrue(carga.aparicion_ids.procedimiento_id.fecha_apertura)

    def test_work_related_services_preview_commit_and_idempotence(self):
        row = self.list_row('LA-50-GYR-050GYR032-N-990-2026')
        row[9] = 'SERVICIOS RELACIONADOS CON LA OBRA'
        tipo = self.env.ref('licitaciones_publicas.tipo_sro')
        self.assertEqual(tipo.code, 'SRO')
        self.assertFalse(tipo.clave_identificador)
        self.assertNotEqual(tipo, self.env.ref('licitaciones_publicas.tipo_ser'))
        self.assertNotEqual(tipo, self.env.ref('licitaciones_publicas.tipo_obr'))
        carga = self.load([row])
        self.assertEqual(carga.procedimientos_nuevos, 1)
        self.assertFalse(self.env['licitacion.procedimiento'].search([('identificador', '=', row[1])]))
        carga._confirm()
        procedure = carga.aparicion_ids.procedimiento_id
        self.assertEqual(procedure.tipo_contratacion_id, tipo)
        self.assertEqual(carga.aparicion_ids.datos_snapshot['tipo_codigo'], 'SRO')
        row[9] = '  Servicios  relacionados con la obra  '
        second = self.load([row])
        self.assertEqual((second.procedimientos_nuevos, second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 0, 1))
        second._confirm()
        self.assertEqual(second.aparicion_ids.procedimiento_id, procedure)
        self.assertEqual(self.env['licitacion.tipo.contratacion'].search_count([('code', '=', 'SRO')]), 1)

    def test_seed_catalogs_and_client_descriptions(self):
        self.assertEqual(self.env['licitacion.tipo.archivo'].search_count([]), 6)
        prefixes = self.env['licitacion.tipo.procedimiento'].search([])
        self.assertEqual(set(prefixes.mapped('prefijo')), {'LA', 'IA', 'LI', 'LO'})
        self.assertEqual(set(prefixes.mapped('descripcion')), {'Por definir por cliente'})
        p = self.procedure()
        self.assertFalse(p.ordenamiento_legal)
        p.tipo_procedimiento_id.descripcion = 'Nombre elegido por el cliente'
        self.assertEqual(p.tipo_procedimiento_id.descripcion, 'Nombre elegido por el cliente')

    def test_catalog_json_constraints_and_unique_code(self):
        config = self.env.ref('licitaciones_publicas.tipo_archivo_detalle_bienes')
        for values in ({'hojas': 0}, {'fila_encabezado': 0}, {'total_columnas': 0},
                       {'palabras_clave_deteccion': '{mal json'}, {'mapeo_columnas': '{"state": ["Estado"]}'}):
            with self.subTest(values=values), self.assertRaises(ValidationError), self.env.cr.savepoint():
                config.write(values)
        # El helper de Odoo espera una clase y revierte su propio savepoint.
        with mute_logger('odoo.sql_db'), self.assertRaises(UniqueViolation):
            config.copy({'codigo': config.codigo})
        self.assertEqual(config.search([('codigo', '=', config.codigo)]), config)

    def test_unknown_prefix_preserved_as_load_incident_without_procedure(self):
        identifier = 'ZZ-50-GYR-050GYR032-N-990-2026'
        carga = self.load([self.list_row(identifier)])
        self.assertFalse(carga.incidencia_ids)
        carga._confirm()
        self.assertFalse(self.env['licitacion.procedimiento'].search([('identificador', '=', identifier)]))
        incident = carga.incidencia_ids
        self.assertEqual((incident.origen, incident.campo, incident.severidad), ('carga', 'prefijo_identificador', 'bloqueante'))
        self.assertEqual(incident.identificador_observado, identifier)
        self.assertTrue(carga.archivo)
        self.env['licitacion.tipo.procedimiento'].create({'prefijo': 'ZZ', 'descripcion': 'Definido por cliente'})
        incident._resolve('resolver', 'El cliente completó el catálogo; se volverá a importar.')
        second = self.load([self.list_row(identifier)])
        second._confirm()
        p = self.env['licitacion.procedimiento'].search([('identificador', '=', identifier)])
        self.assertTrue(p)
        self.assertEqual(p.entidad_id.code, '32')
        self.assertFalse(p.ordenamiento_legal)

    def test_unknown_character_and_inactive_prefix_are_incidents(self):
        prefix = self.env.ref('licitaciones_publicas.prefijo_la')
        prefix.activo = False
        carga = self.load([self.list_row('LA-50-GYR-050GYR032-X-991-2026')])
        carga._confirm()
        self.assertEqual(set(carga.incidencia_ids.mapped('campo')), {'prefijo_identificador', 'caracter_identificador'})

    def test_pending_identifier_does_not_abort_valid_rows_or_create_orphan_entity_conflict(self):
        self.env['licitacion.unidad.compradora'].create({
            'code': '050GYR032', 'name': 'Unidad registrada',
            'entidad_id': self.env.ref('licitaciones_publicas.entidad_01').id})
        invalid = self.list_row('ZZ-50-GYR-050GYR032-N-990-2026')
        valid = self.list_row('LA-50-GYR-050GYR033-N-991-2026')
        carga = self.load([invalid, valid])
        carga._confirm()
        self.assertEqual(carga.incidencia_ids.campo, 'prefijo_identificador')
        self.assertEqual(carga.aparicion_ids.procedimiento_id.identificador, valid[1])
        second = self.load([valid])
        self.assertEqual(second.procedimientos_gone, 0)
        second._confirm()

    def test_config_change_rejects_stale_preview(self):
        p = self.procedure()
        carga = self.preview(p)
        config = carga.tipo_archivo_id
        config.secuencia += 1
        with self.assertRaisesRegex(UserError, 'previsualización'):
            carga._confirm()
        self.assertFalse(p.partida_ids)
        carga._prepare()
        carga._confirm()
        self.assertEqual(carga.configuracion_snapshot['secuencia'], config.secuencia)

    def test_catalog_change_rejects_stale_preview(self):
        p = self.procedure()
        carga = self.preview(p)
        sai = self.env['licitacion.clave.sai'].search([('code', '=', '21601')])
        sai.cucop_ids = [Command.clear()]
        with self.assertRaisesRegex(UserError, 'previsualización'):
            carga._confirm()
        carga._prepare()
        carga._confirm()
        self.assertEqual(carga.incidencia_ids.campo, 'cucop_sai')
        self.assertEqual(carga.incidencia_ids.severidad, 'advertencia')

    def test_services_without_quantity_are_draft_and_idempotent(self):
        p = self.procedure(tipo='ser')
        rows = [[1, 21601, '21601-0028', 'Servicio', 'Servicio de prueba', 'SERVICIO']]
        carga = self.load(rows, HEADERS[:-1], p.identificador + '.xlsx')
        self.assertTrue(carga.detalle_borrador)
        self.assertEqual(carga.subtipo_detectado, 'detalle_servicios')
        carga._confirm()
        self.assertTrue(p.partida_ids.cantidad_pendiente)
        self.assertFalse(carga.incidencia_ids)
        second = self.load(rows, HEADERS[:-1], p.identificador + '.xlsx')
        self.assertEqual((second.partidas_cambios, second.partidas_sin_cambios), (0, 1))
        p.action_pasar_a_analisis()
        self.assign(p.partida_ids, self.companies[:1])
        exp = self.env['licitacion.expediente'].create({'procedimiento_id': p.id, 'company_id': self.companies[0].id})
        with self.assertRaisesRegex(ValidationError, 'cantidad'), self.env.cr.savepoint():
            self.env['licitacion.costeo.linea'].create({'expediente_id': exp.id, 'partida_id': p.partida_ids.id,
                                                      'costo_unitario': 10, 'precio_unitario': 20})
        self.assertIn('Cantidades', exp.bloqueantes_pendientes)

    def test_filename_vs_content_warning_without_reassigning_parent(self):
        p = self.procedure()
        config = self.env.ref('licitaciones_publicas.tipo_archivo_detalle_bienes')
        config.total_columnas = 8
        rows = [[1, 21601, '21601-0028', 'Fibra', 'Fibra verde', 'PIEZA', 5,
                 'LA-50-GYR-050GYR032-T-991-2026']]
        carga = self.load(rows, HEADERS + ['Número de identificación'], p.identificador + '.xlsx')
        carga._confirm()
        self.assertEqual(carga.procedimiento_id, p)
        self.assertEqual(carga.incidencia_ids.severidad, 'advertencia')
        self.assertEqual(carga.incidencia_ids.campo, 'asignacion_archivo')
        self.assertFalse(carga.nota_asignacion)
        carga.incidencia_ids._resolve('resolver', 'Se verificó el archivo con el cliente; se conserva el padre.')
        self.assertEqual(carga.incidencia_ids.state, 'resuelta')
        self.assertEqual(carga.procedimiento_id, p)

    def test_sai_load_previews_and_populates_both_catalogs_idempotently(self):
        headers = ['Partida específica', 'Clave CUCoP+', 'Descripción SAI', 'Descripción CUCoP+', *[f'Otro {n}' for n in range(6)]]
        rows = [[29999, '29999-0001', 'Partida prueba', 'Clave prueba'], [29999, '29999-0002', 'Partida prueba', 'Segunda clave']]
        carga = self.load(rows, headers, 'Libro1.xlsx')
        self.assertFalse(self.env['licitacion.clave.sai'].search([('code', '=', '29999')]))
        carga._confirm()
        sai = self.env['licitacion.clave.sai'].search([('code', '=', '29999')])
        self.assertEqual(set(sai.cucop_ids.mapped('code')), {'29999-0001', '29999-0002'})
        second = self.load(rows, headers, 'Libro1.xlsx')
        self.assertEqual(len(second.prepared_json['diff']['sin_cambios']), 1)
        second._confirm()

    def test_normal_user_cannot_edit_new_catalogs_or_read_other_company_pending_rows(self):
        user = security_tests.TestSecurity.restricted_user(self)
        for model, values in [('licitacion.tipo.procedimiento', {'prefijo': 'ZZ', 'descripcion': 'Sin permiso'}),
                              ('licitacion.caracter.procedimiento', {'clave': 'X', 'descripcion': 'Sin permiso'}),
                              ('licitacion.clave.sai', {'code': '12345', 'name': 'Sin permiso'})]:
            with self.subTest(model=model), self.assertRaises(AccessError):
                self.env[model].with_user(user).create(values)
        config = self.env.ref('licitaciones_publicas.tipo_archivo_detalle_bienes')
        with self.assertRaises(AccessError):
            config.with_user(user).write({'secuencia': 5})
        with self.env.cr.savepoint():
            other_env = self.env(context=dict(self.env.context, allowed_company_ids=[self.companies[1].id]))
            wizard = other_env['licitacion.carga.wizard'].create({'archivo': excel([self.list_row('ZZ-50-GYR-050GYR032-N-995-2026')], LIST_HEADERS),
                'archivo_nombre': 'InformaciónPública_export_otro.xlsx'})
            action = wizard.action_preview()
            other_env[action['res_model']].browse(action['res_id']).action_confirm()
            incidents = other_env['licitacion.incidencia'].search([('identificador_observado', '=', 'ZZ-50-GYR-050GYR032-N-995-2026')])
            with self.assertRaises(AccessError):
                incidents.with_user(user).with_context(allowed_company_ids=[self.companies[0].id]).read(['valor_encontrado'])
