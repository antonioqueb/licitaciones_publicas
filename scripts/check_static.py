"""Structural checks; deliberately not a substitute for Odoo installation."""
import ast
import csv
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
# Selection de ir.actions.act_window.target en Odoo 19.
WINDOW_TARGETS = {'current', 'new', 'fullscreen', 'main'}


def check_expression(expression, where, errors):
    """Comprueba sintaxis sin evaluar dominios ni ejecutar llamadas/contextos."""
    try:
        ast.parse(expression.strip(), filename=where, mode='eval')
    except SyntaxError as error:
        errors.append(f'{where}: expresión inválida: {error.msg}')


def check_python_expressions(tree, where, errors):
    for node in ast.walk(tree):
        if (isinstance(node, ast.keyword) and node.arg in ('domain', 'context')
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            check_expression(node.value.value, f'{where}:{node.lineno} ({node.arg})', errors)


def check_xml_expressions(doc, where, errors):
    for node in doc.iter():
        for key, value in node.attrib.items():
            if key in ('domain', 'context', 'invisible', 'readonly', 'required', 'eval', 'column_invisible') or key.startswith('decoration-'):
                check_expression(value, f'{where} <{node.tag}> ({key})', errors)
        if node.tag == 'field' and node.get('name') in ('domain', 'context') and node.text and node.text.strip():
            check_expression(node.text, f'{where} <field name="{node.get("name")}">', errors)


def check_window_actions(doc, where, errors):
    for record in doc.findall('.//record[@model="ir.actions.act_window"]'):
        target = record.find('field[@name="target"]')
        if target is not None and 'eval' not in target.attrib:
            value = (target.text or '').strip()
            if value not in WINDOW_TARGETS:
                errors.append(f'{where} {record.get("id", "ir.actions.act_window")}: '
                              f'target no admitido en Odoo 19: {value!r}')


def main():
    errors = []
    manifest = ast.literal_eval((ROOT / '__manifest__.py').read_text())
    declared = manifest['data'] + manifest.get('demo', [])
    for files in manifest.get('assets', {}).values():
        declared += [str(Path(f).relative_to(ROOT.name)) for f in files]
    for name in declared:
        if not (ROOT / name).is_file():
            errors.append('Archivo de manifest ausente: ' + name)
    models, inherited = {}, []
    for source in ROOT.rglob('*.py'):
        tree = ast.parse(source.read_text(), filename=str(source))
        check_python_expressions(tree, str(source.relative_to(ROOT)), errors)
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            name, inherits, flds, methods = None, [], {}, set()
            for node in cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(node.name)
                if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
                    continue
                key = node.targets[0].id
                if key in ('_name', '_inherit'):
                    value = ast.literal_eval(node.value)
                    if key == '_name':
                        name = value
                    else:
                        inherits = [value] if isinstance(value, str) else value
                elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'fields':
                    call = node.value
                    relation = call.args[0].value if call.func.attr in ('Many2one', 'Many2many', 'One2many') and call.args and isinstance(call.args[0], ast.Constant) else None
                    flds[key] = relation
            if name:
                models[name] = {'fields': flds, 'methods': methods, 'inherit': inherits}
            elif inherits:
                inherited.append((inherits[0], flds, methods))
    for name, flds, methods in inherited:
        models.setdefault(name, {'fields': {}, 'methods': set(), 'inherit': []})['fields'].update(flds)
        models[name]['methods'].update(methods)
    for _ in range(6):
        for name, info in models.items():
            for parent in info['inherit']:
                if parent in models:
                    info['fields'] = {**models[parent]['fields'], **info['fields']}
                    info['methods'] |= models[parent]['methods']
    generic = {'id', 'display_name', 'create_date', 'write_date', 'create_uid', 'write_uid', 'activity_ids', 'message_ids'}

    def check_arch(node, model, where):
        if model not in models or not model.startswith('licitacion.'):
            return
        info = models[model]
        for child in node:
            if child.tag == 'field':
                name = child.get('name')
                if name not in info['fields'] and name not in generic:
                    errors.append(f'{where}: campo inexistente {model}.{name}')
                if len(child):
                    relation = info['fields'].get(name)
                    if relation:
                        check_arch(child, relation, where)
                    else:
                        check_arch(child, model, where)
            else:
                if child.tag == 'button' and child.get('type') == 'object' and child.get('name') not in info['methods']:
                    errors.append(f'{where}: método inexistente {model}.{child.get("name")}')
                if child.tag == 'tree' or 'attrs' in child.attrib:
                    errors.append(f'{where}: sintaxis de vistas antigua')
                check_arch(child, model, where)

    xmlids = set()
    for path in ROOT.rglob('*.xml'):
        doc = ET.parse(path)
        check_xml_expressions(doc, str(path.relative_to(ROOT)), errors)
        check_window_actions(doc, str(path.relative_to(ROOT)), errors)
        for rec in doc.findall('.//record'):
            xmlid = rec.get('id')
            if xmlid in xmlids:
                errors.append('XML ID duplicado: ' + xmlid)
            xmlids.add(xmlid)
            if rec.get('model') == 'ir.ui.view' and rec.find("field[@name='inherit_id']") is None:
                model = rec.findtext("field[@name='model']")
                check_arch(rec.find("field[@name='arch']"), model, str(path.relative_to(ROOT)))
    for row in csv.DictReader((ROOT / 'security/ir.model.access.csv').open()):
        reference = row['model_id:id']
        if not any(reference == 'model_' + name.replace('.', '_') for name in models):
            errors.append('Modelo ACL inexistente: ' + reference)
        if not row['group_id:id']:
            errors.append('ACL pública inesperada: ' + row['id'])
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'OK: {len(list(ROOT.rglob("*.py")))} Python, {len(list(ROOT.rglob("*.xml")))} XML; manifest, campos, botones, ACL, expresiones y acciones coherentes.')


if __name__ == '__main__':
    main()
