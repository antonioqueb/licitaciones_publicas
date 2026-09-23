import base64
import io

import openpyxl
from odoo import Command, fields
from odoo.tests import Form
from odoo.tests.common import TransactionCase

from ..models.common import IMPORT_TOKEN

HEADERS = ['Núm.', 'Partida específica', 'Clave CUCoP+', 'Descripción CUCoP+', 'Descripción detallada', 'Unidad de medida', 'Cantidad solicitada']


def excel(rows, headers=HEADERS, blanks=0):
    workbook = openpyxl.Workbook()
    workbook.active.title = "sheet1"
    for _ in range(blanks):
        workbook.active.append([None])
    workbook.active.append(headers)
    for row in rows:
        workbook.active.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return base64.b64encode(out.getvalue())


class LicitacionCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.companies = cls.env['res.company'].create([
            {'name': 'Prueba licitante A', 'currency_id': cls.env.ref('base.MXN').id},
            {'name': 'Prueba licitante B', 'currency_id': cls.env.ref('base.MXN').id},
            {'name': 'Prueba licitante C', 'currency_id': cls.env.ref('base.MXN').id},
        ])
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.companies.ids, mail_create_nosubscribe=True, tracking_disable=True))
        cucops = cls.env['licitacion.clave.cucop'].create([
            {'code': f'21601-{n:04}', 'name': f'CUCoP de prueba {n}'} for n in range(1, 51)])
        cls.env['licitacion.clave.sai'].create({'code': '21601', 'name': 'Partida SAI de prueba', 'cucop_ids': [Command.set(cucops.ids)]})
        cls.unit = cls.env['licitacion.unidad.compradora'].search([('code', '=', '050GYR032')], limit=1) or cls.env['licitacion.unidad.compradora'].create({'code': '050GYR032', 'name': 'Unidad de prueba'})
        cls.reason = cls.env.ref('licitaciones_publicas.motivo_no_giro')
        cls.partner = cls.env['res.partner'].create({'name': 'Proveedor de prueba', 'es_proveedor_licitacion': True, 'email': 'supplier@example.invalid', 'company_id': False})

    def procedure(self, number=89, tipo='adq'):
        return self.env['licitacion.procedimiento'].create({
            'identificador': f'IA-50-GYR-050GYR032-N-{number}-2026',
            'nombre_publicado': 'Procedimiento de prueba', 'unidad_compradora_id': self.unit.id,
            'tipo_contratacion_id': self.env.ref('licitaciones_publicas.tipo_' + tipo).id})

    def partida(self, procedure, number=1):
        return self.env['licitacion.partida'].with_context(_lp_import=IMPORT_TOKEN).create({
            'procedimiento_id': procedure.id, 'numero': number, 'partida_especifica': '21601',
            'clave_cucop': f'21601-{number:04}', 'descripcion_detallada': f'Fibra {number}',
            'unidad_medida': 'PIEZA', 'cantidad': 10, 'importada': True})

    def assign(self, partida, companies=None):
        return self.env['licitacion.partida.empresa'].create([
            {'partida_id': partida.id, 'company_id': company.id} for company in (companies or self.companies)])

    def modal_form(self, action):
        model = self.env[action['res_model']].with_context(**action.get('context', {}))
        return Form(model.browse(action.get('res_id')))

    def full_expedientes(self):
        procedure = self.procedure()
        procedure.action_pasar_a_analisis()
        line = self.partida(procedure)
        self.assign(line)
        self.env['licitacion.partida.proveedor'].create({'partida_id': line.id, 'partner_id': self.partner.id})
        wizard = self.modal_form(procedure.action_generar_expedientes()).save()
        wizard.action_generate()
        return procedure, line, procedure.expediente_ids.sorted('company_id')

    def preview(self, procedure, rows=None, filename=None, day='2026-09-21', blanks=0):
        rows = rows or [[1, 21601, '21601-0028', 'FIBRA', 'Fibra verde', 'PIEZA', 4000]]
        wizard = self.env['licitacion.carga.wizard'].create({'archivo': excel(rows, blanks=blanks),
            'archivo_nombre': filename or procedure.identificador + '.xlsx', 'fecha_snapshot': day})
        action = self.content_preview(wizard)
        if action.get('res_id'):
            return self.env[action['res_model']].browse(action['res_id']).carga_id
        return self.env['licitacion.carga'].browse(action['context']['default_carga_id'])

    def content_preview(self, wizard):
        """Content-diff regression tests explicitly force a repeated binary.

        DEV-03 tests call action_preview directly to exercise the upload gate.
        """
        action = wizard.action_preview()
        if action['res_model'] == 'licitacion.carga.wizard':
            form = self.modal_form(wizard.action_force())
            form.motivo = 'Prueba de idempotencia del contenido con reimportación intencional.'
            form.confirmado = True
            action = form.save().action_confirm()
        return action
