"""Reproduce seed catalogs and ACLs. Run from any directory."""
import csv
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def write(path, content):
    (ROOT / path).write_text(content, encoding='utf-8')


def record(xmlid, model, vals):
    return '<record id="%s" model="%s">%s</record>\n' % (xmlid, model, ''.join(
        '<field name="%s">%s</field>' % (k, escape(str(v))) for k, v in vals.items()))


def generate():
    models = ['procedimiento', 'partida', 'partida.empresa', 'partida.proveedor', 'expediente', 'pregunta',
              'costeo.linea', 'documento', 'documento.version', 'carta.apoyo', 'carga', 'aparicion', 'incidencia', 'fecha.fatal']
    catalogs = ['unidad.compradora', 'estatus.portal', 'motivo.descarte', 'tipo.contratacion', 'entidad.federativa', 'clave.cucop', 'tipo.archivo', 'tipo.procedimiento', 'caracter.procedimiento', 'clave.sai']
    wizards = ['carga.wizard', 'asignar.procedimiento.wizard', 'preview.wizard', 'preview.line', 'criba.wizard',
               'generar.expedientes.wizard', 'resolver.incidencia.wizard', 'propagar.empresas.wizard', 'propagar.proveedores.wizard']
    with (ROOT / 'security/ir.model.access.csv').open('w') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['id', 'name', 'model_id:id', 'group_id:id', 'perm_read', 'perm_write', 'perm_create', 'perm_unlink'])
        for name in models + catalogs + wizards:
            slug = name.replace('.', '_')
            perms = [1, 1, 1, int(name in wizards or name in ('partida.empresa', 'partida.proveedor'))]
            if name in catalogs or name == 'fecha.fatal':
                perms = [1, 0, 0, 0]
            if name in ('aparicion', 'documento.version'):
                perms = [1, 0, 1, 0]
            writer.writerow(['access_' + slug, name, 'model_licitacion_' + slug, 'group_licitaciones_user', *perms])
            if name in catalogs:
                writer.writerow(['access_' + slug + '_manager', name + ' manager', 'model_licitacion_' + slug,
                                 'group_licitaciones_manager', 1, 1, 1, 0])
    security = '''<odoo>
<record id="module_category_licitaciones" model="ir.module.category"><field name="name">Licitaciones Públicas</field></record>
<record id="privilege_licitaciones" model="res.groups.privilege"><field name="name">Licitaciones Públicas</field><field name="category_id" ref="module_category_licitaciones"/></record>
<record id="group_licitaciones_user" model="res.groups"><field name="name">Usuario de Licitaciones</field><field name="privilege_id" ref="privilege_licitaciones"/><field name="implied_ids" eval="[(4, ref('base.group_user'))]"/></record>
<record id="group_licitaciones_manager" model="res.groups"><field name="name">Administrador de Licitaciones</field><field name="privilege_id" ref="privilege_licitaciones"/><field name="implied_ids" eval="[(4, ref('group_licitaciones_user'))]"/><field name="user_ids" eval="[(4, ref('base.user_admin'))]"/></record>
'''
    for name in models:
        if name in ['expediente', 'pregunta', 'costeo.linea', 'documento', 'documento.version', 'carta.apoyo', 'partida.empresa']:
            domain = "[('company_id', 'in', company_ids)]"
        elif name == 'incidencia':
            domain = "['|', '&', ('procedimiento_id', '!=', False), '|', ('procedimiento_id.company_ids', '=', False), ('procedimiento_id.company_ids', 'in', company_ids), '&', ('procedimiento_id', '=', False), ('carga_id.company_ids', 'in', company_ids)]"
        elif name == 'carga':
            domain = "[('company_ids', 'in', company_ids)]"
        else:
            prefix = '' if name == 'procedimiento' else 'partida_id.procedimiento_id.' if name == 'partida.proveedor' else 'procedimiento_id.'
            domain = f"['|', ('{prefix}company_ids', '=', False), ('{prefix}company_ids', 'in', company_ids)]"
        slug = name.replace('.', '_')
        security += f'<record id="rule_{slug}" model="ir.rule"><field name="name">{name}: empresas activas</field><field name="model_id" ref="model_licitacion_{slug}"/><field name="domain_force">{escape(domain)}</field></record>\n'
    write('security/licitaciones_security.xml', security + '</odoo>\n')
    states = ['Aguascalientes', 'Baja California', 'Baja California Sur', 'Campeche', 'Coahuila de Zaragoza',
              'Colima', 'Chiapas', 'Chihuahua', 'Ciudad de México', 'Durango', 'Guanajuato', 'Guerrero', 'Hidalgo',
              'Jalisco', 'México', 'Michoacán de Ocampo', 'Morelos', 'Nayarit', 'Nuevo León', 'Oaxaca', 'Puebla',
              'Querétaro', 'Quintana Roo', 'San Luis Potosí', 'Sinaloa', 'Sonora', 'Tabasco', 'Tamaulipas',
              'Tlaxcala', 'Veracruz de Ignacio de la Llave', 'Yucatán', 'Zacatecas']
    data = '<odoo noupdate="1">\n'
    for n, state in enumerate(states, 1):
        data += record(f'entidad_{n:02}', 'licitacion.entidad.federativa', {'code': f'{n:02}', 'name': state})
    for code, name, key in [('ADQ', 'Adquisiciones', 'I'), ('SER', 'Servicios', 'S'), ('OBR', 'Obra pública', 'O'), ('ARR', 'Arrendamientos', 'A')]:
        data += record('tipo_' + code.lower(), 'licitacion.tipo.contratacion', {'code': code, 'name': name, 'clave_identificador': key})
    for code, name in [('NO_GIRO', 'Fuera de nuestro giro'), ('OBRA_PUBLICA', 'Obra pública'), ('ENTIDAD_FUERA', 'Entidad fuera de cobertura'), ('SIN_CLAVES', 'Sin claves de interés'), ('PLAZO_INVIABLE', 'Plazo inviable')]:
        data += record('motivo_' + code.lower(), 'licitacion.motivo.descarte', {'code': code, 'name': name, 'aplica_a': 'ambos'})
    for code, name in [('VIGENTE', 'Vigente'), ('EN_ACLARACIONES', 'En aclaraciones'), ('EN_REPREGUNTAS', 'En repreguntas'), ('EN_ATENCION_DE_PREGUNTAS', 'En atención de preguntas')]:
        data += record('estatus_' + code.lower(), 'licitacion.estatus.portal', {'code': code, 'name': name})
    for code, name in [('21601', 'Aseo y limpieza'), ('24901', 'Pulidores'), ('27201', 'Equipo de protección'), ('21101', 'Papel')]:
        data += record('cucop_' + code, 'licitacion.clave.cucop', {'code': code, 'name': name})
    write('data/catalog_data.xml', data + '</odoo>\n')
    sequences = '<odoo noupdate="1">\n'
    for xmlid, name, code, prefix, padding in [('seq_expediente_folio', 'Folio de expediente', 'licitacion.expediente', 'EXP-%(year)s-', 4), ('seq_carta_apoyo', 'Folio de carta', 'licitacion.carta.apoyo', 'CARTA-%(year)s-', 5)]:
        sequences += f'<record id="{xmlid}" model="ir.sequence"><field name="name">{name}</field><field name="code">{code}</field><field name="prefix">{prefix}</field><field name="padding">{padding}</field><field name="company_id" eval="False"/></record>\n'
    write('data/sequences.xml', sequences + '</odoo>')
    write('demo/demo_data.xml', '<odoo noupdate="1">' + record('uc_demo_032', 'licitacion.unidad.compradora', {'code': '050GYR032', 'name': 'Unidad compradora 032 — demostración', 'dependencia': 'IMSS (referencia de prueba)'}) + '</odoo>')
    crons = '<odoo noupdate="1">\n'
    for xmlid, name, model, code in [('juntas_72', 'Juntas de aclaraciones en 72 horas', 'procedimiento', 'model._cron_recordatorio_juntas(72)'), ('juntas_24', 'Juntas sin atender en 24 horas', 'procedimiento', 'model._cron_recordatorio_juntas(24)'), ('incidencias', 'Escalar incidencias bloqueantes', 'incidencia', 'model._cron_escalar()'), ('documentos', 'Vencimiento de documentos', 'documento', 'model._cron_vencimientos()')]:
        crons += f'<record id="cron_{xmlid}" model="ir.cron"><field name="name">{name}</field><field name="model_id" ref="model_licitacion_{model}"/><field name="state">code</field><field name="code">{code}</field><field name="interval_number">1</field><field name="interval_type">hours</field><field name="active">True</field></record>\n'
    write('data/cron.xml', crons + '</odoo>')


if __name__ == '__main__':
    generate()
