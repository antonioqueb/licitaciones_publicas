/** @odoo-module **/
/**
 * Centro de Licitaciones: acción de cliente única que enruta a cada espacio guiado según `lp_view`.
 *
 *   inicio          tablero con agenda, alertas y accesos guiados
 *   procedimientos  lista de procedimientos con filtros por etapa y semáforo
 *   procedimiento   flujo guiado de un procedimiento (criba → renglones → expedientes → … → fallo)
 *   expedientes     lista de expedientes por empresa
 *   expediente      armado guiado de un expediente (preguntas, costeo, documentos, cartas)
 *   carga           importación paso a paso del Excel del portal
 *
 * Los botones «Vista guiada» de los formularios nativos llegan con `active_model`/`active_id`.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { LpInicio } from "./inicio";
import { LpProcedimientos } from "./procedimientos";
import { LpProcedimiento } from "./procedimiento";
import { LpExpedientes } from "./expedientes";
import { LpExpediente } from "./expediente";
import { LpCarga } from "./carga";
import { HUB_TAG } from "./meta";

export class LpHub extends Component {
    static template = "licitaciones_publicas.Hub";
    static components = { LpInicio, LpProcedimientos, LpProcedimiento, LpExpedientes, LpExpediente, LpCarga };
    static props = ["*"];

    setup() {
        const context = this.props.action?.context || {};
        let view = context.lp_view;
        let recordId = context.lp_id || null;
        if (!view && context.active_model === "licitacion.procedimiento" && context.active_id) {
            view = "procedimiento";
            recordId = context.active_id;
        } else if (!view && context.active_model === "licitacion.expediente" && context.active_id) {
            view = "expediente";
            recordId = context.active_id;
        }
        this.view = view || "inicio";
        this.recordId = recordId;
        this.filters = context.lp_filters || {};
    }
}

registry.category("actions").add(HUB_TAG, LpHub);
