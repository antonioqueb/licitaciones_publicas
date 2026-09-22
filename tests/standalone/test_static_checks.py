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


class TestWindowActions(unittest.TestCase):
    def test_removed_window_target_is_reported(self):
        doc = ET.fromstring('''<odoo>
            <record id="settings" model="ir.actions.act_window">
                <field name="target">inline</field>
            </record>
        </odoo>''')
        errors = []
        static.check_window_actions(doc, 'settings.xml', errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("settings.xml settings", errors[0])
        self.assertIn("'inline'", errors[0])

    def test_odoo_19_targets_and_default_are_accepted(self):
        records = ''.join(
            '<record model="ir.actions.act_window">'
            f'<field name="target">{target}</field></record>'
            for target in ('current', 'new', 'fullscreen', 'main'))
        doc = ET.fromstring(f'<odoo>{records}<record model="ir.actions.act_window"/></odoo>')
        errors = []
        static.check_window_actions(doc, 'actions.xml', errors)
        self.assertEqual(errors, [])

    def test_url_actions_and_view_fields_use_separate_rules(self):
        doc = ET.fromstring('''<odoo>
            <record model="ir.actions.act_url"><field name="target">self</field></record>
            <record model="ir.ui.view"><field name="arch" type="xml">
                <form><field name="target"/></form>
            </field></record>
        </odoo>''')
        errors = []
        static.check_window_actions(doc, 'actions.xml', errors)
        self.assertEqual(errors, [])
