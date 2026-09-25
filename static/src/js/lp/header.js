/** @odoo-module **/
import { Component } from "@odoo/owl";
import { useLp } from "./nav";

/**
 * Encabezado común de cada espacio: contexto (eyebrow), título, subtítulo, navegación entre espacios
 * y una ranura de acciones principales. En móvil las acciones pasan debajo del título.
 */
export class LpHeader extends Component {
    static template = "licitaciones_publicas.LpHeader";
    static props = {
        eyebrow: { type: String, optional: true },
        title: String,
        subtitle: { type: String, optional: true },
        current: { type: String, optional: true },
        tone: { type: String, optional: true },
        slots: { type: Object, optional: true },
    };

    setup() {
        this.lp = useLp();
        this.tabs = [
            { key: "inicio", label: "Inicio", icon: "fa-home", go: () => this.lp.goInicio() },
            { key: "procedimientos", label: "Procedimientos", icon: "fa-list-ol", go: () => this.lp.goProcedimientos() },
            { key: "expedientes", label: "Expedientes", icon: "fa-folder-open-o", go: () => this.lp.goExpedientes() },
            { key: "carga", label: "Nueva carga", icon: "fa-cloud-upload", go: () => this.lp.goCarga() },
            { key: "agenda", label: "Agenda", icon: "fa-calendar", go: () => this.lp.openXmlAction("licitaciones_publicas.action_agenda", { clearBreadcrumbs: true }) },
        ];
    }
}
