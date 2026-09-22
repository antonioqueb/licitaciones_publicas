/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Native editable one2many owns mutations. Chips reflect unsaved assignments too.
export class PartidaEmpresasChips extends Component {
    static template = "licitaciones_publicas.PartidaEmpresasChips";
    static props = { ...standardFieldProps };

    get companies() {
        const data = this.props.record.data;
        const assignments = data.partida_empresa_ids?.records;
        if (assignments) {
            return [...assignments]
                .filter((r) => r.data.company_id)
                .sort((a, b) => a.data.sequence - b.data.sequence || (a.resId || 0) - (b.resId || 0))
                .map((r, index) => {
                    const company = r.data.company_id;
                    return { key: r.id, name: company[1] || company.display_name, principal: index === 0 };
                });
        }
        const main = data.empresa_principal_id;
        const mainId = Array.isArray(main) ? main[0] : main?.id;
        return (data[this.props.name]?.records || []).map((r) => ({
            key: r.id, name: r.data.display_name, principal: r.resId === mainId,
        }));
    }
}

registry.category("fields").add("partida_empresas_chips", {
    component: PartidaEmpresasChips,
    supportedTypes: ["many2many"],
    relatedFields: () => [{ name: "display_name", type: "char" }],
});
