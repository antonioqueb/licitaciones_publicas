/** @odoo-module **/
/**
 * Metadatos de presentación del Centro de Licitaciones.
 *
 * Aquí no hay reglas de negocio: solo etiquetas, tonos de color, iconos y textos de guía para cada
 * estado que ya define el servidor. Las etiquetas oficiales de las selecciones se leen de `fields_get`
 * (ver data.js) y estas tablas solo aportan la parte visual (tono, icono, pista).
 */
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, deserializeDateTime, formatDate, formatDateTime } from "@web/core/l10n/dates";

// En Odoo 19 luxon es un global del cliente web, no un módulo importable.
const { DateTime } = luxon;

export const HUB_TAG = "licitaciones_publicas.hub";

/** Etapas del procedimiento en el orden del flujo (los cierres por criba se muestran aparte). */
export const PROC_FLOW = ["detectado", "analisis", "preguntas", "costeo", "propuesta", "con_fallo"];

export const PROC_META = {
    detectado: { tone: "slate", icon: "fa-search", short: _t("Criba"),
        hint: _t("Revisa las fechas fatales y decide si participamos, descartamos o no es viable.") },
    analisis: { tone: "info", icon: "fa-list-ol", short: _t("Renglones"),
        hint: _t("Asigna empresas y proveedores a cada renglón. Después genera los expedientes.") },
    preguntas: { tone: "info", icon: "fa-question-circle-o", short: _t("Preguntas"),
        hint: _t("Captura en cada expediente las preguntas para la junta de aclaraciones.") },
    costeo: { tone: "warn", icon: "fa-calculator", short: _t("Costeo"),
        hint: _t("Captura costos y precios por empresa. La secundaria debe superar el margen de la principal.") },
    propuesta: { tone: "primary", icon: "fa-paper-plane-o", short: _t("Propuesta"),
        hint: _t("Completa los documentos bloqueantes y publica la propuesta de cada expediente.") },
    con_fallo: { tone: "ok", icon: "fa-gavel", short: _t("Fallo"),
        hint: _t("El procedimiento ya tiene fallo. El expediente queda como evidencia.") },
    descartado: { tone: "muted", icon: "fa-ban", terminal: true,
        hint: _t("Descartado por criba. Se reabre solo si el portal publica fechas límite nuevas.") },
    no_viable: { tone: "danger", icon: "fa-times-circle-o", terminal: true,
        hint: _t("Declarado no viable. Puede reabrirse manualmente desde Cribar.") },
};

export const EXP_FLOW = ["borrador", "en_armado", "listo", "publicado"];
export const EXP_META = {
    borrador: { tone: "slate", icon: "fa-file-o", hint: _t("Expediente creado. Comienza el armado para capturar preguntas, costeo y documentos.") },
    en_armado: { tone: "info", icon: "fa-wrench", hint: _t("Captura preguntas, costeo y documentos. Resuelve los bloqueantes para marcarlo listo.") },
    listo: { tone: "warn", icon: "fa-check-square-o", hint: _t("Todo completo. Publica la propuesta cuando el equipo lo autorice.") },
    publicado: { tone: "ok", icon: "fa-flag-checkered", hint: _t("Propuesta publicada internamente. Este estado no publica en ComprasMX.") },
};

export const JUNTA_META = {
    sin_fecha: { tone: "muted", icon: "fa-calendar-o" },
    normal: { tone: "ok", icon: "fa-calendar-check-o" },
    urgente: { tone: "warn", icon: "fa-exclamation-triangle" },
    vencida: { tone: "danger", icon: "fa-calendar-times-o" },
};

export const PARTICIPACION_META = {
    sin_decidir: { tone: "muted", icon: "fa-circle-o" },
    participamos: { tone: "ok", icon: "fa-check-circle" },
    descartada: { tone: "danger", icon: "fa-ban" },
};

export const DOC_STATE_META = {
    pendiente: { tone: "muted", icon: "fa-clock-o" },
    en_gestion: { tone: "info", icon: "fa-refresh" },
    recibido: { tone: "ok", icon: "fa-check" },
    vencido: { tone: "danger", icon: "fa-exclamation-circle" },
    no_aplica: { tone: "slate", icon: "fa-minus" },
};

export const CARGA_STATE_META = {
    borrador: { tone: "slate" }, previsualizada: { tone: "info" }, confirmada: { tone: "ok" },
    rechazada: { tone: "danger" }, pendiente_asignacion: { tone: "warn" },
};

export const INCIDENCIA_META = {
    abierta: { tone: "warn" }, resuelta: { tone: "ok" }, ignorada: { tone: "muted" },
};

export const PREGUNTA_META = {
    borrador: { tone: "slate" }, revision_legal: { tone: "warn" }, lista: { tone: "info" }, enviada: { tone: "primary" }, respondida: { tone: "ok" },
};

export const CARTA_META = { borrador: { tone: "slate" }, enviada: { tone: "info" }, respondida: { tone: "ok" } };

/** Las cinco fechas fatales, en el orden natural del procedimiento. */
export const FECHAS = [
    { field: "fecha_limite_preguntas", tipo: "preguntas", label: _t("Límite de preguntas"), icon: "fa-question" },
    { field: "fecha_junta_aclaraciones", tipo: "junta", label: _t("Junta de aclaraciones"), icon: "fa-users" },
    { field: "fecha_entrega_muestras", tipo: "muestras", label: _t("Entrega de muestras"), icon: "fa-flask" },
    { field: "fecha_apertura", tipo: "apertura", label: _t("Apertura"), icon: "fa-envelope-open-o" },
    { field: "fecha_fallo", tipo: "fallo", label: _t("Fallo"), icon: "fa-gavel" },
];

// ----------------------------------------------------------------------------- helpers de datos
/** Normaliza un many2one venga como [id, nombre] (search_read) o como {id, display_name} (web_search_read). */
export function m2o(value) {
    if (!value) return null;
    if (Array.isArray(value)) return { id: value[0], name: value[1] || "" };
    if (typeof value === "object") return { id: value.id, name: value.display_name || value.name || "" };
    return { id: value, name: "" };
}

export function toDateTime(value) {
    if (!value) return null;
    if (DateTime.isDateTime(value)) return value;
    return value.length > 10 ? deserializeDateTime(value) : deserializeDate(value);
}

export function fmtDateTime(value) {
    const dt = toDateTime(value);
    return dt ? formatDateTime(dt) : "—";
}

export function fmtDate(value) {
    const dt = toDateTime(value);
    return dt ? formatDate(dt) : "—";
}

/** "en 3 días", "hace 2 horas": la distancia relativa que guía la urgencia. */
export function relative(value) {
    const dt = toDateTime(value);
    return dt ? dt.toRelative({ locale: "es" }) || "" : "";
}

/** Horas que faltan (negativas si ya pasó). */
export function hoursUntil(value) {
    const dt = toDateTime(value);
    return dt ? dt.diffNow("hours").hours : null;
}

/** Tono de urgencia de una fecha: vencida, en 72 h, próxima, sin fecha. */
export function dateTone(value) {
    const hours = hoursUntil(value);
    if (hours === null) return "muted";
    if (hours < 0) return "danger";
    if (hours <= 72) return "warn";
    return "ok";
}

export function money(amount, currency = "MXN") {
    try {
        return new Intl.NumberFormat("es-MX", { style: "currency", currency: currency || "MXN", maximumFractionDigits: 2 }).format(amount || 0);
    } catch {
        return (amount || 0).toFixed(2);
    }
}

export function number(value, digits = 2) {
    return new Intl.NumberFormat("es-MX", { maximumFractionDigits: digits }).format(value || 0);
}

export function pct(value) {
    return `${number(value, 2)} %`;
}

export function initials(name) {
    return (name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
}

/** Índice de la etapa en el flujo lineal (los cierres por criba devuelven -1). */
export function stepIndex(state) {
    return PROC_FLOW.indexOf(state);
}

export function tone(meta, key) {
    return (meta[key] && meta[key].tone) || "slate";
}
