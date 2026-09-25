/** @odoo-module **/
/**
 * Capa de lectura del Centro de Licitaciones.
 *
 * Solo consultas: `search_read`, `formatted_read_group`, `search_count` y `fields_get` sobre los modelos
 * existentes, siempre con los permisos y reglas por empresa del usuario. Las acciones de negocio se
 * siguen ejecutando con los métodos del servidor (`action_*`) desde cada pantalla.
 */
import { DateTime } from "luxon";
import { serializeDateTime } from "@web/core/l10n/dates";
import { m2o } from "./meta";

export const MODELS = {
    proc: "licitacion.procedimiento",
    partida: "licitacion.partida",
    partidaProv: "licitacion.partida.proveedor",
    partidaEmp: "licitacion.partida.empresa",
    exp: "licitacion.expediente",
    pregunta: "licitacion.pregunta",
    costeo: "licitacion.costeo.linea",
    doc: "licitacion.documento",
    carta: "licitacion.carta.apoyo",
    incidencia: "licitacion.incidencia",
    carga: "licitacion.carga",
    cargaWizard: "licitacion.carga.wizard",
    fecha: "licitacion.fecha.fatal",
    entidad: "licitacion.entidad.federativa",
};

export const PROC_FIELDS = [
    "identificador", "nombre_publicado", "state", "junta_class", "fecha_junta_aclaraciones", "fecha_limite_preguntas",
    "fecha_entrega_muestras", "fecha_apertura", "fecha_fallo", "fecha_fallo_original", "fallo_diferido",
    "unidad_compradora_id", "entidad_id", "tipo_contratacion_id", "estatus_portal_id", "user_id", "company_ids",
    "sigue_apareciendo", "fecha_ya_no_aparece", "renglones_count", "renglones_con_empresa_count",
    "renglones_descartados_count", "incidencias_abiertas_count", "motivo_descarte_id", "nota_criba",
    "reapertura_habilitada", "codigo_expediente", "tipo_procedimiento", "caracter", "ejercicio",
    "tipo_procedimiento_id", "caracter_procedimiento_id", "write_date", "active",
];
export const PROC_CARD_FIELDS = [
    "identificador", "nombre_publicado", "state", "junta_class", "fecha_junta_aclaraciones", "fecha_apertura",
    "unidad_compradora_id", "entidad_id", "estatus_portal_id", "user_id", "company_ids", "sigue_apareciendo",
    "renglones_count", "renglones_con_empresa_count", "incidencias_abiertas_count", "write_date",
];
export const PARTIDA_FIELDS = [
    "numero", "partida_especifica", "clave_cucop", "descripcion_cucop", "descripcion_detallada", "unidad_medida",
    "cantidad", "cantidad_pendiente", "cantidad_min", "cantidad_max", "participacion", "motivo_descarte_id",
    "company_ids", "empresa_principal_id", "sigue_apareciendo", "importada",
];
export const EXP_FIELDS = [
    "folio", "procedimiento_id", "company_id", "state", "partidas_count", "proveedores_count", "preguntas_count",
    "total_costo", "total_precio", "margen_bruto", "margen_pct", "currency_id", "bloqueantes_pendientes", "write_date",
];
export const DOC_FIELDS = ["tipo", "origen", "partner_id", "partida_id", "state", "fecha_recepcion", "fecha_vencimiento", "monto", "bloqueante", "archivo_nombre", "nota"];
export const PREGUNTA_FIELDS = ["sequence", "partida_id", "texto", "autor_id", "fecha", "state", "respuesta_portal"];
export const COSTEO_FIELDS = ["partida_id", "proveedor_id", "cantidad", "costo_unitario", "precio_unitario", "total_costo", "total_precio", "margen_pct", "recargo_secundaria_pct", "es_secundaria"];
export const CARTA_FIELDS = ["folio", "partner_id", "state", "fecha_envio", "fecha_respuesta", "partida_ids"];
export const INCIDENCIA_FIELDS = ["procedimiento_id", "partida_id", "carga_id", "origen", "campo", "valor_esperado", "valor_encontrado", "severidad", "state", "create_date", "es_valor_no_reconocido", "identificador_observado"];
export const FECHA_FIELDS = ["name", "procedimiento_id", "tipo", "fecha", "state", "user_id"];
export const CARGA_FIELDS = ["archivo_nombre", "fecha_snapshot", "tipo_detectado", "subtipo_detectado", "alcance", "registros", "state", "resumen", "user_id", "procesado_el", "reimportacion_forzada", "procedimiento_id"];

// ----------------------------------------------------------------------------- etiquetas oficiales
let labelsPromise = null;

/** Etiquetas de las selecciones tal como las define el servidor (una sola lectura por sesión). */
export function loadLabels(orm) {
    if (!labelsPromise) {
        const wanted = {
            [MODELS.proc]: ["state", "junta_class"],
            [MODELS.partida]: ["participacion"],
            [MODELS.exp]: ["state"],
            [MODELS.doc]: ["tipo", "state", "origen"],
            [MODELS.pregunta]: ["state"],
            [MODELS.carta]: ["state"],
            [MODELS.incidencia]: ["origen", "severidad", "state"],
            [MODELS.carga]: ["state", "tipo_detectado", "subtipo_detectado", "origen_portal"],
            [MODELS.fecha]: ["tipo"],
        };
        labelsPromise = Promise.all(Object.entries(wanted).map(async ([model, names]) => {
            const spec = await orm.call(model, "fields_get", [names], { attributes: ["selection", "string"] });
            const out = {};
            for (const name of names) {
                out[name] = Object.fromEntries((spec[name] && spec[name].selection) || []);
            }
            return [model, out];
        })).then((pairs) => Object.fromEntries(pairs)).catch((error) => {
            labelsPromise = null;
            throw error;
        });
    }
    return labelsPromise;
}

export function label(labels, model, field, key) {
    return (labels && labels[model] && labels[model][field] && labels[model][field][key]) || key || "—";
}

// ----------------------------------------------------------------------------- agregados
function nowSql() {
    return serializeDateTime(DateTime.now());
}

function inHours(hours) {
    return serializeDateTime(DateTime.now().plus({ hours }));
}

export async function countByState(orm, domain = []) {
    const groups = await orm.formattedReadGroup(MODELS.proc, domain, ["state"], ["__count"]);
    const counts = {};
    for (const group of groups) {
        const key = Array.isArray(group.state) ? group.state[0] : group.state;
        counts[key] = group.__count;
    }
    return counts;
}

/** Datos del tablero de inicio, en paralelo. */
export async function loadInicio(orm) {
    const relevant = [["state", "not in", ["descartado", "no_viable", "con_fallo"]]];
    const [counts, urgentes, vencidas, incidencias, expedientes, cargas, agenda, recientes, atencion] = await Promise.all([
        countByState(orm),
        orm.searchCount(MODELS.proc, [...relevant, ["junta_class", "=", "urgente"]]),
        orm.searchCount(MODELS.proc, [["state", "=", "detectado"], ["junta_class", "=", "vencida"]]),
        orm.searchRead(MODELS.incidencia, [["state", "=", "abierta"]], INCIDENCIA_FIELDS, { limit: 8, order: "severidad desc, create_date desc" }),
        orm.searchRead(MODELS.exp, [["state", "in", ["en_armado", "listo"]]], EXP_FIELDS, { limit: 8, order: "write_date desc" }),
        orm.searchRead(MODELS.carga, [["state", "in", ["borrador", "previsualizada", "pendiente_asignacion"]]], CARGA_FIELDS, { limit: 5, order: "id desc" }),
        orm.searchRead(MODELS.fecha, [["fecha", ">=", nowSql()], ["fecha", "<=", inHours(24 * 7)], ["state", "not in", ["descartado", "no_viable", "con_fallo"]]], FECHA_FIELDS, { limit: 40, order: "fecha asc" }),
        orm.searchRead(MODELS.proc, relevant, PROC_CARD_FIELDS, { limit: 6, order: "write_date desc" }),
        orm.searchRead(MODELS.proc, [["state", "=", "detectado"]], PROC_CARD_FIELDS, { limit: 6, order: "fecha_junta_aclaraciones asc, id desc" }),
    ]);
    const [bloqueantes, ultimaCarga] = await Promise.all([
        orm.searchCount(MODELS.incidencia, [["state", "=", "abierta"], ["severidad", "=", "bloqueante"]]),
        orm.searchRead(MODELS.carga, [["state", "=", "confirmada"]], CARGA_FIELDS, { limit: 1, order: "fecha_confirmacion desc, id desc" }),
    ]);
    return { counts, urgentes, vencidas, incidencias, bloqueantes, expedientes, cargas, agenda, recientes, atencion, ultimaCarga: ultimaCarga[0] || null };
}

/** Lista de procedimientos con filtros (texto, estado, entidad, semáforo, responsable). */
export async function loadProcedimientos(orm, { query = "", state = "", entidad = 0, junta = "", mine = false, ausentes = false, offset = 0, limit = 24, uid = 0 } = {}) {
    // El dominio base (sin el estado) alimenta los contadores por etapa; el estado solo filtra la lista.
    const base = [];
    if (query) {
        base.push("|", "|", ["identificador", "ilike", query], ["nombre_publicado", "ilike", query], ["unidad_compradora_id", "ilike", query]);
    }
    if (entidad) base.push(["entidad_id", "=", entidad]);
    if (junta) base.push(["junta_class", "=", junta]);
    if (mine && uid) base.push(["user_id", "=", uid]);
    if (ausentes) base.push(["sigue_apareciendo", "=", false]);
    const domain = [...base];
    if (state === "__relevantes") domain.push(["state", "not in", ["descartado", "no_viable", "con_fallo"]]);
    else if (state) domain.push(["state", "=", state]);
    const [records, total, counts, entidades] = await Promise.all([
        orm.searchRead(MODELS.proc, domain, PROC_CARD_FIELDS, { limit, offset, order: "fecha_apertura desc, identificador" }),
        orm.searchCount(MODELS.proc, domain),
        countByState(orm, base),
        orm.searchRead(MODELS.entidad, [], ["id", "nombre"], { limit: 40, order: "code" }),
    ]);
    return { records, total, counts, entidades: entidades.map((e) => ({ id: e.id, name: e.nombre || e.display_name })) };
}

/** Un procedimiento completo: ficha, renglones con proveedores, expedientes, incidencias abiertas. */
export async function loadProcedimiento(orm, id) {
    const [record] = await orm.read(MODELS.proc, [id], PROC_FIELDS);
    if (!record) return null;
    const [partidas, expedientes, incidencias, apariciones] = await Promise.all([
        orm.searchRead(MODELS.partida, [["procedimiento_id", "=", id]], PARTIDA_FIELDS, { order: "partida_especifica, numero, id" }),
        orm.searchRead(MODELS.exp, [["procedimiento_id", "=", id]], EXP_FIELDS, { order: "company_id" }),
        orm.searchRead(MODELS.incidencia, [["procedimiento_id", "=", id], ["state", "=", "abierta"]], INCIDENCIA_FIELDS, { order: "severidad desc, create_date desc" }),
        orm.searchCount("licitacion.aparicion", [["procedimiento_id", "=", id]]),
    ]);
    const proveedores = partidas.length
        ? await orm.searchRead(MODELS.partidaProv, [["partida_id", "in", partidas.map((p) => p.id)]], ["partida_id", "partner_id"], { order: "id" })
        : [];
    const byPartida = {};
    for (const row of proveedores) {
        const pid = m2o(row.partida_id).id;
        (byPartida[pid] = byPartida[pid] || []).push(m2o(row.partner_id));
    }
    for (const partida of partidas) partida.proveedores = byPartida[partida.id] || [];
    return { record, partidas, expedientes, incidencias, apariciones };
}

/** Lista de expedientes (todas las empresas activas). */
export async function loadExpedientes(orm, { query = "", state = "", offset = 0, limit = 24 } = {}) {
    const domain = [];
    if (query) domain.push("|", ["folio", "ilike", query], ["procedimiento_id", "ilike", query]);
    if (state) domain.push(["state", "=", state]);
    const [records, total, groups] = await Promise.all([
        orm.searchRead(MODELS.exp, domain, EXP_FIELDS, { limit, offset, order: "write_date desc" }),
        orm.searchCount(MODELS.exp, domain),
        orm.formattedReadGroup(MODELS.exp, [], ["state"], ["__count"]),
    ]);
    const counts = {};
    for (const group of groups) counts[Array.isArray(group.state) ? group.state[0] : group.state] = group.__count;
    return { records, total, counts };
}

/** Un expediente completo: preguntas, costeo, documentos, cartas y renglones de su empresa. */
export async function loadExpediente(orm, id) {
    const [record] = await orm.read(MODELS.exp, [id], [...EXP_FIELDS, "partida_ids", "proveedor_ids"]);
    if (!record) return null;
    const procId = m2o(record.procedimiento_id).id;
    const [preguntas, costeo, documentos, cartas, partidas, [proc]] = await Promise.all([
        orm.searchRead(MODELS.pregunta, [["expediente_id", "=", id]], PREGUNTA_FIELDS, { order: "sequence, id" }),
        orm.searchRead(MODELS.costeo, [["expediente_id", "=", id]], COSTEO_FIELDS, { order: "partida_id" }),
        orm.searchRead(MODELS.doc, [["expediente_id", "=", id]], DOC_FIELDS, { order: "origen, tipo, id" }),
        orm.searchRead(MODELS.carta, [["expediente_id", "=", id]], CARTA_FIELDS, { order: "folio" }),
        record.partida_ids.length ? orm.read(MODELS.partida, record.partida_ids, PARTIDA_FIELDS) : [],
        orm.read(MODELS.proc, [procId], ["identificador", "nombre_publicado", "state", "fecha_apertura", "fecha_junta_aclaraciones", "fecha_limite_preguntas", "unidad_compradora_id"]),
    ]);
    return { record, preguntas, costeo, documentos, cartas, partidas, proc };
}

/** Cargas confirmadas del mismo binario: la misma consulta que hace el servidor, con los permisos del usuario. */
export function loadCargasDelArchivo(orm, sha) {
    if (!sha) return Promise.resolve([]);
    return orm.searchRead(MODELS.carga, [["binary_sha256", "=", sha.toLowerCase()], ["state", "=", "confirmada"]], CARGA_FIELDS, { order: "id desc" });
}
