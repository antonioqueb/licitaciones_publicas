"""Functional 101: preserve every listing row and correct catalogs explicitly."""
import json

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import LicitacionCase
from . import test_dynamic_import as dynamic_tests
from . import test_security as security_tests
from ..catalog_resolution import CATALOGS, catalog_norm
from ..models.common import IMPORT_TOKEN
from ..models.importer import LicitacionImporter


@tagged('post_install', '-at_install')
class TestCatalogCrossings(LicitacionCase):
    load = dynamic_tests.TestDynamicImport.load
    list_row = dynamic_tests.TestDynamicImport.list_row

    def row(self):
        return self.list_row('LA-50-GYR-050GYR032-N-990-2026')

    def test_veracruz_alias_and_base_states_unchanged(self):
        entity = self.env.ref('licitaciones_publicas.entidad_30')
        states = self.env['res.country.state'].search([('country_id', '=', self.env.ref('base.mx').id)])
        before = states.read(['name', 'code', 'write_date'])
        entity.nombres_alternativos = '  véracruz , VERACRUZ DE LA LLAVE , VERACRUZ'
        self.assertEqual(entity.nombres_alternativos, 'VERACRUZ, VERACRUZ DE LA LLAVE')
        for text in ('VERACRUZ', ' veracruz de la llave '):
            row = self.row()
            row[12] = text
            carga = self.load([row])
            carga._confirm()
            self.assertFalse(carga.incidencia_ids)
            self.assertEqual(carga.aparicion_ids.procedimiento_id.entidad_id, entity)
        self.assertEqual(before, states.read(['name', 'code', 'write_date']))
        self.assertEqual(entity.nombre, entity.estado_base_id.name)
        entities = entity.search([])
        self.assertEqual(len(entities), 32)
        self.assertEqual(len(entities.estado_base_id), 32)

    def test_all_six_unknown_values_confirm_every_row(self):
        row = self.row()
        row[1], row[5], row[9], row[12] = 'ZZ-50-GYR-050GYR999-X-990-2026', 'Estatus nuevo 101', 'Contratación no catalogada', 'MARTE'
        carga = self.load([row, self.row()])
        self.assertFalse(carga.incidencia_ids)
        self.assertFalse(self.env['licitacion.estatus.portal'].search([('name', '=', row[5])]))
        carga._confirm()
        self.assertEqual(carga.state, 'confirmada')
        self.assertEqual(len(carga.aparicion_ids), 2)
        self.assertEqual(set(carga.incidencia_ids.mapped('campo')), set(CATALOGS))
        self.assertEqual(len(carga.incidencia_ids), 6)
        self.assertEqual(set(carga.incidencia_ids.mapped('severidad')), {'advertencia'})
        procedure = carga.aparicion_ids.procedimiento_id.filtered(lambda p: p.identificador == row[1])
        self.assertFalse(procedure.unidad_compradora_id)
        self.assertFalse(procedure.tipo_contratacion_id)
        self.assertFalse(procedure.entidad_id)
        self.assertEqual(procedure.catalogos_portal['entidad_federativa'], 'MARTE')
        self.assertEqual(procedure.estatus_portal_id.tipo, 'auto_creado')
        self.assertEqual(procedure.estatus_portal_id.estado, 'por_revisar')
        for incident in carga.incidencia_ids:
            self.assertEqual(incident.procedimiento_id, procedure)
            detail = json.loads(incident.detalle)
            self.assertEqual((detail['fila'], detail['archivo'], detail['identificador']), (2, carga.archivo_nombre, row[1]))
            self.assertTrue(incident.activity_ids)
            self.assertTrue(incident.activity_ids.user_id.has_group('licitaciones_publicas.group_licitaciones_manager'))
        second = self.load([row, self.row()])
        self.assertEqual((second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 2))

    def test_table_resolves_each_catalog_only(self):
        carga = self.load([self.row()])
        importer = LicitacionImporter.for_carga(carga)
        cases = {'entidad_federativa': ('Zacatecas', 'entidad_32'),
                 'estatus_portal': ('vigente', 'estatus_vigente'),
                 'tipo_contratacion': ('  adquisiciónes  ', 'tipo_adq'),
                 'tipo_procedimiento': ('la', 'prefijo_la'),
                 'caracter_procedimiento': ('n', 'caracter_n'),
                 'unidad_compradora': ('050gyr032', None)}
        for campo, (text, xmlid) in cases.items():
            with self.subTest(campo=campo):
                expected = self.env.ref('licitaciones_publicas.' + xmlid) if xmlid else self.unit
                self.assertEqual(importer.resolve_catalog_value(campo, text), expected)
                self.assertFalse(importer.resolve_catalog_value(campo, 'ZZZ VALOR AJENO ZZZ'))
        self.assertEqual(catalog_norm('  México\n  país '), 'MEXICO PAIS')

    def test_entity_resolution_wizard_persists_alias_and_chatter(self):
        row = self.row()
        row[12] = 'MARTE'
        carga = self.load([row])
        carga._confirm()
        incident = carga.incidencia_ids
        entity = self.env.ref('licitaciones_publicas.entidad_30')
        form = self.modal_form(incident.action_resolver())
        self.assertTrue(form.es_catalogo)
        with self.assertRaises(AssertionError):
            form.save()
        form.entidad_federativa_id = entity
        form.nota = 'Portal confirmó que MARTE correspondía a Veracruz.'
        form.save().action_apply()
        self.assertEqual(incident.state, 'resuelta')
        self.assertTrue(incident.fecha_resolucion)
        self.assertEqual(incident.resuelta_por_id, self.env.user)
        self.assertEqual(incident.procedimiento_id.entidad_id, entity)
        self.assertIn('MARTE', entity.nombres_alternativos)
        self.assertTrue(incident.procedimiento_id.message_ids.filtered(lambda m: 'MARTE correspondía' in (m.body or '')))
        second = self.load([row])
        second._confirm()
        self.assertFalse(second.incidencia_ids)

    def test_ignore_requires_note_and_keeps_business_values(self):
        row = self.row()
        self.load([row])._confirm()
        row[12] = 'MARTE'
        carga = self.load([row])
        carga._confirm()
        incident = carga.incidencia_ids
        procedure = incident.procedimiento_id
        self.assertEqual(procedure.entidad_id, self.env.ref('licitaciones_publicas.entidad_32'))
        second = self.load([row])
        self.assertEqual((second.procedimientos_cambios, second.procedimientos_sin_cambios), (0, 1))
        before = procedure.read(['entidad_id', 'unidad_compradora_id', 'catalogos_portal', 'state'])
        with self.assertRaises(ValidationError):
            incident._resolve('ignorar', '   ')
        incident._resolve('ignorar', 'Valor informado por el portal; se conserva evidencia.')
        self.assertEqual(before, procedure.read(['entidad_id', 'unidad_compradora_id', 'catalogos_portal', 'state']))
        self.assertEqual(incident.state, 'ignorada')
        self.assertTrue(procedure.message_ids.filtered(lambda m: 'se conserva evidencia' in (m.body or '')))

    def test_generic_warning_cannot_be_blocking_or_resolved_by_normal_user(self):
        row = self.row()
        row[12] = 'MARTE'
        carga = self.load([row])
        carga._confirm()
        incident = carga.incidencia_ids
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env['licitacion.incidencia'].with_context(_lp_import=IMPORT_TOKEN).create({
                'carga_id': carga.id, 'procedimiento_id': incident.procedimiento_id.id, 'origen': 'procedimiento',
                'campo': 'entidad_federativa', 'es_valor_no_reconocido': True, 'severidad': 'bloqueante'})
        user = security_tests.TestSecurity.restricted_user(self)
        with self.assertRaises(AccessError):
            incident.with_user(user).with_context(allowed_company_ids=self.companies[:1].ids)._resolve('ignorar', 'No autorizado')
        user.group_ids = [Command.link(self.env.ref('licitaciones_publicas.group_licitaciones_manager').id)]
        entity = self.env.ref('licitaciones_publicas.entidad_30').with_user(user)
        with self.assertRaises(AccessError):
            entity.write({'name': 'Cambiar nombre oficial'})
        entity.write({'nombres_alternativos': ' un alias '})
        self.assertEqual(entity.nombres_alternativos, 'UN ALIAS')

    def test_resolution_checks_catalog_and_stale_target(self):
        row = self.row()
        row[12] = 'MARTE'
        carga = self.load([row])
        carga._confirm()
        incident = carga.incidencia_ids
        with self.assertRaises(ValidationError):
            incident._resolve('resolver', 'Catálogo incorrecto', self.unit)
        entity = self.env.ref('licitaciones_publicas.entidad_30')
        other = self.load([list(row)])
        other._confirm()
        incident._resolve('resolver', 'Se asigna Veracruz.', entity)
        with self.assertRaisesRegex(UserError, 'cambió'):
            other.incidencia_ids._resolve('resolver', 'Otro intento.', self.env.ref('licitaciones_publicas.entidad_32'))

    def test_alias_change_invalidates_preview(self):
        row = self.row()
        row[12] = 'MARTE'
        carga = self.load([row])
        self.env.ref('licitaciones_publicas.entidad_30').nombres_alternativos = 'MARTE'
        with self.assertRaisesRegex(UserError, 'previsualización'):
            carga._confirm()
        carga._prepare()
        carga._confirm()
        self.assertFalse(carga.incidencia_ids)
