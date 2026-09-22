import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..parser import profile_config, ImportValidationError

TIPOS_DATO = [('listado', 'Listado de procedimientos'), ('detalle_bienes', 'Detalle de bienes'),
              ('detalle_servicios', 'Detalle de servicios'), ('detalle_rangos', 'Detalle con rangos'),
              ('catalogo', 'Catálogo SAI'), ('anexo', 'Anexo')]
CONFIG_FIELDS = ('name', 'codigo', 'patron_nombre', 'hojas', 'hoja_nombre', 'fila_encabezado',
                 'total_columnas', 'tipo_dato', 'origen', 'palabras_clave_deteccion',
                 'encabezados_esperados', 'mapeo_columnas', 'secuencia', 'activo')


class TipoArchivo(models.Model):
    _name = 'licitacion.tipo.archivo'
    _description = 'Tipo de archivo de importación'
    _inherit = 'licitacion.retained'
    _order = 'secuencia, codigo'

    name = fields.Char(string='Nombre', required=True)
    codigo = fields.Char(string='Código', required=True, index=True)
    patron_nombre = fields.Char(string='Patrones de nombre', help='Glob separados por comas. El nombre no determina el significado del identificador.')
    hojas = fields.Integer(string='Número de hojas', required=True, default=1)
    hoja_nombre = fields.Char(string='Hoja objetivo', default='sheet1', help='Vacío: primera hoja. Se compara sin acentos ni diferencias de mayúsculas.')
    fila_encabezado = fields.Integer(string='Fila de encabezado', required=True, default=1)
    total_columnas = fields.Integer(string='Columnas esperadas', required=True)
    tipo_dato = fields.Selection(TIPOS_DATO, string='Tipo de dato', required=True)
    origen = fields.Char(string='Origen', required=True, default='Compras MX')
    palabras_clave_deteccion = fields.Text(string='Palabras clave (JSON)', help='Array: ["ESTATUS", "UNIDAD COMPRADORA"].')
    encabezados_esperados = fields.Text(string='Encabezados esperados (JSON)',
        help='Objeto {"cols": ["NÚM.", ...]}. Opcional: "columnas_alternativas": [7]. Coincidencia mínima: 70%.')
    mapeo_columnas = fields.Text(string='Mapeo de columnas (JSON)',
        help='Campo técnico: array de nombres aceptados. Ejemplo: {"identificador": ["NÚMERO DE IDENTIFICACIÓN"]}. No admite expresiones ni campos arbitrarios.')
    secuencia = fields.Integer(string='Prioridad', required=True, default=10)
    activo = fields.Boolean(string='Activo', default=True, required=True)
    detalle_borrador = fields.Boolean(string='Detalle en borrador', compute='_compute_borrador')
    _codigo_unique = models.Constraint('UNIQUE(codigo)', 'El código del tipo de archivo debe ser único.')

    @api.depends('tipo_dato')
    def _compute_borrador(self):
        for rec in self:
            rec.detalle_borrador = rec.tipo_dato.startswith('detalle_') if rec.tipo_dato else False

    def _configuration(self):
        self.ensure_one()
        return {'id': self.id, **{key: self[key] for key in CONFIG_FIELDS}}

    @api.constrains(*CONFIG_FIELDS)
    def _check_configuration(self):
        for rec in self:
            if not re.fullmatch(r'[a-z][a-z0-9_]*', rec.codigo or ''):
                raise ValidationError('Use un código técnico en minúsculas, sin espacios.')
            try:
                profile_config(rec._configuration())
            except ImportValidationError as exc:
                raise ValidationError(str(exc)) from exc


class TipoProcedimiento(models.Model):
    _name = 'licitacion.tipo.procedimiento'
    _description = 'Prefijo de procedimiento'
    _inherit = 'licitacion.retained'
    _rec_name = 'prefijo'
    _order = 'prefijo'

    prefijo = fields.Char(string='Prefijo', size=2, required=True, index=True)
    descripcion = fields.Char(string='Descripción del cliente', required=True)
    activo = fields.Boolean(string='Activo', required=True, default=True)
    _prefijo_unique = models.Constraint('UNIQUE(prefijo)', 'El prefijo debe ser único.')

    @api.constrains('prefijo')
    def _check_prefijo(self):
        if any(not re.fullmatch('[A-Z]{2}', rec.prefijo or '') for rec in self):
            raise ValidationError('El prefijo debe contener dos letras mayúsculas.')


class CaracterProcedimiento(models.Model):
    _name = 'licitacion.caracter.procedimiento'
    _description = 'Clave de carácter del procedimiento'
    _inherit = 'licitacion.retained'
    _rec_name = 'clave'
    _order = 'clave'

    clave = fields.Char(string='Clave', size=1, required=True, index=True)
    descripcion = fields.Char(string='Descripción del cliente', required=True)
    _clave_unique = models.Constraint('UNIQUE(clave)', 'La clave debe ser única.')

    @api.constrains('clave')
    def _check_clave(self):
        if any(not re.fullmatch('[A-Z]', rec.clave or '') for rec in self):
            raise ValidationError('La clave debe contener una letra mayúscula.')


class ClaveSai(models.Model):
    _name = 'licitacion.clave.sai'
    _description = 'Partida SAI y claves CUCoP+ permitidas'
    _inherit = 'licitacion.catalogo'

    cucop_ids = fields.Many2many('licitacion.clave.cucop', string='Claves CUCoP+ permitidas')
