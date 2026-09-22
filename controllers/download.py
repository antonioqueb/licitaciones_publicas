import io
import zipfile

from odoo import http
from odoo.http import request, content_disposition
from werkzeug.exceptions import BadRequest, NotFound


class LicitacionDownload(http.Controller):
    @http.route('/licitaciones/cartas.zip', type='http', auth='user', methods=['GET'])
    def cartas_zip(self, ids='', **kwargs):
        try:
            numbers = list(dict.fromkeys(int(value) for value in ids.split(',')))
            if not numbers or len(numbers) > 100 or min(numbers) < 1:
                raise ValueError()
        except ValueError as exc:
            raise BadRequest('Seleccione entre 1 y 100 expedientes.') from exc
        expedientes = request.env['licitacion.expediente'].browse(numbers)
        expedientes.check_access('read')
        if expedientes.exists() != expedientes or not expedientes.carta_apoyo_ids:
            raise NotFound()
        cartas = expedientes.carta_apoyo_ids
        cartas.check_access('read')
        report = request.env.ref('licitaciones_publicas.report_carta_apoyo')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for carta in cartas:
                content, _fmt = report._render_qweb_pdf(report.report_name, res_ids=carta.ids)
                archive.writestr('%s.pdf' % carta.folio.replace('/', '-'), content)
        return request.make_response(stream.getvalue(), headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', content_disposition('Cartas.zip')),
            ('Cache-Control', 'private, no-store'),
        ])
