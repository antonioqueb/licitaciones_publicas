/** @odoo-module **/
/**
 * Navegación y ejecución de acciones del Centro de Licitaciones.
 *
 * Cada pantalla es la misma acción de cliente (`licitaciones_publicas.hub`) con un `lp_view` distinto,
 * así el cliente web conserva migas de pan y el botón Atrás. Las acciones de negocio se ejecutan con
 * los métodos `action_*` existentes: si devuelven una acción (asistente, formulario, descarga) se abre
 * con el cliente web y al cerrarse se recarga la pantalla.
 */
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { HUB_TAG } from "./meta";

export const VIEW_TITLES = {
    inicio: _t("Centro de Licitaciones"),
    procedimientos: _t("Procedimientos"),
    procedimiento: _t("Procedimiento"),
    expedientes: _t("Expedientes"),
    expediente: _t("Expediente"),
    carga: _t("Nueva carga"),
};

export function useLp() {
    const orm = useService("orm");
    const action = useService("action");
    const dialog = useService("dialog");
    const notification = useService("notification");

    const client = (view, { name, context } = {}) => ({
        type: "ir.actions.client", tag: HUB_TAG, name: name || VIEW_TITLES[view],
        context: { lp_view: view, ...(context || {}) },
    });

    const notify = (error) => {
        const message = error?.data?.message || error?.message || String(error);
        notification.add(message, { type: "danger", sticky: true });
    };

    return {
        orm, action, dialog, notification, notify,
        goInicio: () => action.doAction(client("inicio"), { clearBreadcrumbs: true }),
        goProcedimientos: (filters = {}) => action.doAction(client("procedimientos", { context: { lp_filters: filters } }), { clearBreadcrumbs: true }),
        goExpedientes: (filters = {}) => action.doAction(client("expedientes", { context: { lp_filters: filters } }), { clearBreadcrumbs: true }),
        goCarga: () => action.doAction(client("carga"), { clearBreadcrumbs: true }),
        openProcedimiento: (id, name) => action.doAction(client("procedimiento", { name, context: { lp_id: id } })),
        openExpediente: (id, name) => action.doAction(client("expediente", { name, context: { lp_id: id } })),
        /** Formulario nativo del registro: en la misma vista (con migas) o en un diálogo para capturas rápidas. */
        openRecord: (model, id, { inDialog = false, onClose, context } = {}) => action.doAction({
            type: "ir.actions.act_window", res_model: model, res_id: id || false, views: [[false, "form"]],
            target: inDialog ? "new" : "current", context: context || {},
        }, { onClose }),
        /** Acción nativa por XML ID (listas, calendario, ajustes). */
        openXmlAction: (xmlid, options = {}) => action.doAction(xmlid, options),
        /**
         * Ejecuta un método `action_*` del servidor. Si devuelve una acción la abre; al cerrarla (o de inmediato
         * si no devolvió acción) llama a `reload`. Los errores de negocio se muestran como notificación.
         */
        call: async (model, method, ids, { kwargs = {}, reload, context } = {}) => {
            try {
                const result = await orm.call(model, method, [ids], context ? { ...kwargs, context } : kwargs);
                if (result && typeof result === "object" && result.type) {
                    await action.doAction(result, { onClose: reload });
                } else if (reload) {
                    await reload();
                }
                return result === undefined ? true : result;
            } catch (error) {
                notify(error);
                return null;
            }
        },
        confirm: ({ title, body, confirmLabel, danger }) => new Promise((resolve) => {
            dialog.add(ConfirmationDialog, {
                title, body, confirmLabel: confirmLabel || _t("Confirmar"), cancelLabel: _t("Cancelar"),
                confirmClass: danger ? "btn-danger" : "btn-primary",
                confirm: () => resolve(true), cancel: () => resolve(false), dismiss: () => resolve(false),
            });
        }),
    };
}
