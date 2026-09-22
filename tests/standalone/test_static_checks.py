import ast
import importlib.util
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

spec = importlib.util.spec_from_file_location(
    'lp_static', Path(__file__).resolve().parents[2] / 'scripts/check_static.py')
static = importlib.util.module_from_spec(spec)
spec.loader.exec_module(static)


class TestStaticExpressions(unittest.TestCase):
    def test_malformed_domain_inside_valid_python_is_reported(self):
        broken = "[('aplica_a', 'in', ['procedimiento', 'ambos])]"
        tree = ast.parse(f"motivo = fields.Many2one('motivo', domain={broken!r})")
        errors = []
        static.check_python_expressions(tree, 'workflows.py', errors)
        self.assertEqual(len(errors), 1)
        self.assertIn('workflows.py:1 (domain)', errors[0])

    def test_dynamic_context_is_parsed_without_evaluation(self):
        expression = "[('id', 'in', context.get('allowed_company_ids', []))]"
        tree = ast.parse(f"company = fields.Many2one('res.company', domain={expression!r})")
        errors = []
        static.check_python_expressions(tree, 'model.py', errors)
        # Si se evaluase la expresión, context no existiría y daría NameError.
        self.assertEqual(errors, [])

    def test_bad_xml_modifier_and_action_domain_are_reported(self):
        doc = ET.fromstring('''<odoo>
            <form><field name="motivo_id" invisible="decision not in ("/></form>
            <record model="ir.actions.act_window"><field name="domain">[('active', '=', True)</field></record>
        </odoo>''')
        errors = []
        static.check_xml_expressions(doc, 'views.xml', errors)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any('(invisible)' in error for error in errors))
        self.assertTrue(any('name="domain"' in error for error in errors))

    def test_valid_xml_expressions_are_accepted(self):
        doc = ET.fromstring('''<odoo>
            <field name="motivo_id" invisible="decision not in ('descartar', 'no_viable')"/>
            <field name="context">{'default_company_id': company_id}</field>
            <field name="groups_id" eval="[(4, ref('base.group_user'))]"/>
        </odoo>''')
        errors = []
        static.check_xml_expressions(doc, 'views.xml', errors)
        self.assertEqual(errors, [])
