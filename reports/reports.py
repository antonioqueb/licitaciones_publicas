from odoo import api, models

from .. import xlsx_export
from ..models.expediente import DOCUMENT_TYPES


class CartaPdf(models.AbstractModel):
    _name = 'report.licitaciones_publicas.carta_apoyo'
    _description = 'Carta de solicitud de apoyo'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['licitacion.carta.apoyo'].browse(docids)
        docs.check_access('read')
        return {'doc_ids': docs.ids, 'doc_model': docs._name, 'docs': docs}


class ExpedientePdf(models.AbstractModel):
    _name = 'report.licitaciones_publicas.expediente'
    _description = 'Expediente completo'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['licitacion.expediente'].browse(docids)
        docs.check_access('read')
        return {'doc_ids': docs.ids, 'doc_model': docs._name, 'docs': docs}


class PreguntasPdf(models.AbstractModel):
    _name = 'report.licitaciones_publicas.preguntas_junta'
    _inherit = 'report.licitaciones_publicas.expediente'
    _description = 'Preguntas listas para la junta'


class CosteoXlsx(models.AbstractModel):
    _name = 'report.licitaciones_publicas.costeo_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Exportación de costeo'

    def _get_objs_for_report(self, docids, data):
        docs = self.env['licitacion.expediente'].browse(docids or self.env.context.get('active_ids', []))
        docs.check_access('read')
        return docs

    def generate_xlsx_report(self, workbook, data, docs):
        for index, exp in enumerate(docs, 1):
            rows = [[exp.company_id.name, exp.procedimiento_id.identificador, l.partida_id.numero,
                l.partida_id.clave_cucop, l.partida_id.descripcion_detallada, l.cantidad, l.costo_unitario,
                l.precio_unitario, l.total_costo, l.total_precio, l.margen_pct, l.recargo_secundaria_pct, exp.currency_id.name]
                for l in exp.costeo_linea_ids]
            xlsx_export.costeo(workbook, 'Costeo' if index == 1 else 'Costeo %s' % index, rows)


class PartidasXlsx(models.AbstractModel):
    _name = 'report.licitaciones_publicas.partidas_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Exportación de partidas'

    def _get_objs_for_report(self, docids, data):
        docs = self.env['licitacion.procedimiento'].browse(docids or self.env.context.get('active_ids', []))
        docs.check_access('read')
        return docs

    def generate_xlsx_report(self, workbook, data, docs):
        rows = []
        for p in docs.partida_ids:
            rows.append([p.procedimiento_id.identificador, p.numero, p.partida_especifica, p.clave_cucop,
                p.descripcion_cucop, p.descripcion_detallada, p.unidad_medida, p.cantidad, p.cantidad_min, p.cantidad_max,
                p.empresa_principal_id.name, ', '.join((p.company_ids - p.empresa_principal_id).mapped('name')),
                ', '.join(p.partida_proveedor_ids.partner_id.mapped('name')), dict(p._fields['participacion'].selection)[p.participacion],
                p.motivo_descarte_id.name, p.sigue_apareciendo])
        xlsx_export.partidas(workbook, 'Partidas', rows)


class ChecklistXlsx(models.AbstractModel):
    _name = 'report.licitaciones_publicas.checklist_xlsx'
    _inherit = 'report.licitaciones_publicas.costeo_xlsx'
    _description = 'Checklist documental consolidado'

    def generate_xlsx_report(self, workbook, data, docs):
        rows = []
        for exp in docs:
            for doc in exp.documento_ids:
                rows.append([exp.company_id.name, exp.folio, doc.partner_id.name or 'Documento propio',
                    doc.partida_id.clave_cucop or 'General', dict(DOCUMENT_TYPES)[doc.tipo],
                    dict(doc._fields['state'].selection)[doc.state], doc.fecha_recepcion or '', doc.fecha_vencimiento or '',
                    doc.bloqueante, doc.archivo_nombre or ''])
        xlsx_export.checklist(workbook, 'Checklist', rows)
