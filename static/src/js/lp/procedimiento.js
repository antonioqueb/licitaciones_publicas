/** @odoo-module **/
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { user } from "@web/core/user";
import { LpHeader } from "./header";
import { LpStepper, LpEmpty, LpAvatar } from "./components";
import { useLp } from "./nav";
import { loadProcedimiento, loadLabels, label, MODELS } from "./data";
import {
    PROC_FLOW, PROC_META, JUNTA_META, EXP_META, PARTICIPACION_META, FECHAS,
    m2o, fmtDateTime, fmtDate, relative, dateTone, money, number, pct, stepIndex,
} from "./meta";

/**
 * Flujo guiado de un procedimiento. La etapa la define el servidor (`state`); aquí solo se muestra qué
 * falta para avanzar y se ejecutan las acciones existentes: criba, confirmar análisis, generar
 * expedientes y siguiente etapa. La edición de renglones abre el formulario nativo en un diálogo.
 */
export class LpProcedimiento extends Component {
    static template = "licitaciones_publicas.Procedimiento";
    static components = { LpHeader, LpStepper, LpEmpty, LpAvatar };
    static props = { recordId: { type: [Number, Boolean, { value: null }], optional: true } };

    setup() {
        this.lp = useLp();
        this.flow = PROC_FLOW;
        this.meta = PROC_META;
        this.juntaMeta = JUNTA_META;
        this.expMeta = EXP_META;
        this.partMeta = PARTICIPACION_META;
        this.fechas = FECHAS;
        this.MODELS = MODELS;
        this.m2o = m2o;
        this.name = (value) => (m2o(value) || {}).name || "";
        this.fmtDateTime = fmtDateTime;
        this.fmtDate = fmtDate;
        this.relative = relative;
        this.dateTone = dateTone;
        this.money = money;
        this.number = number;
        this.pct = pct;
        this.companies = Object.fromEntries((user.allowedCompanies || []).map((c) => [c.id, c.name]));
        this.state = useState({ loading: true, labels: null, data: null, tab: null, selected: {}, filter: "todas", query: "", busy: false });
        onWillStart(() => this.load(this.props.recordId));
        onWillUpdateProps((next) => { if (next.recordId !== this.props.recordId) return this.load(next.recordId); });
    }

    async load(id = this.props.recordId) {
        if (!id) {
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            const [labels, data] = await Promise.all([loadLabels(this.lp.orm), loadProcedimiento(this.lp.orm, id)]);
            this.state.labels = labels;
            this.state.data = data;
            if (data) {
                const current = this.tabFor(data.record.state);
                if (!this.state.tab || !this.tabKeys.includes(this.state.tab)) this.state.tab = current;
                if (this.env.config && this.env.config.setDisplayName) this.env.config.setDisplayName(data.record.identificador);
            }
        } catch (error) {
            this.lp.notify(error);
        } finally {
            this.state.loading = false;
        }
    }

    reload() {
        return this.load();
    }

    label(model, field, key) {
        return label(this.state.labels, model, field, key);
    }

    // ------------------------------------------------------------------ etapas
    get rec() {
        return this.state.data ? this.state.data.record : null;
    }

    get steps() {
        return this.flow.map((key) => ({ key, label: this.label(MODELS.proc, "state", key), icon: this.meta[key].icon, hint: this.meta[key].short }));
    }

    get terminal() {
        return this.rec && this.meta[this.rec.state].terminal ? this.rec.state : false;
    }

    /** Etapa mostrada en el paso a paso: en un cierre por criba se resalta la última alcanzada (detectado). */
    get current() {
        return this.terminal ? "detectado" : this.rec.state;
    }

    get currentIndex() {
        return stepIndex(this.current);
    }

    tabFor(state) {
        return { detectado: "criba", analisis: "renglones", preguntas: "expedientes", costeo: "expedientes", propuesta: "expedientes", con_fallo: "expedientes", descartado: "criba", no_viable: "criba" }[state] || "criba";
    }

    get tabKeys() {
        return ["criba", "renglones", "expedientes"];
    }

    /** Al elegir una etapa en el paso a paso se abre la pestaña que le corresponde (solo consulta). */
    selectStep(key) {
        this.state.tab = this.tabFor(key);
    }

    // ------------------------------------------------------------------ lista de verificación
    get partidas() {
        return this.state.data ? this.state.data.partidas : [];
    }

    get expedientes() {
        return this.state.data ? this.state.data.expedientes : [];
    }

    get incidencias() {
        return this.state.data ? this.state.data.incidencias : [];
    }

    get bloqueantesAbiertas() {
        return this.incidencias.filter((i) => i.severidad === "bloqueante");
    }

    get conEmpresa() {
        return this.partidas.filter((p) => p.company_ids.length);
    }

    get conProveedor() {
        return this.conEmpresa.filter((p) => p.proveedores.length);
    }

    /** Requisitos de la etapa actual, con su cumplimiento: la guía "qué falta" del panel superior. */
    get checklist() {
        const r = this.rec;
        if (!r) return [];
        const items = [];
        const ok = (done, text, hint) => items.push({ done, text, hint });
        switch (r.state) {
            case "detectado":
                ok(!!r.fecha_junta_aclaraciones || !!r.fecha_apertura, "Fechas fatales publicadas", "Revisa junta, apertura y fallo antes de decidir.");
                ok(!this.bloqueantesAbiertas.length, "Sin incidencias bloqueantes", this.bloqueantesAbiertas.length ? `${this.bloqueantesAbiertas.length} incidencia(s) bloqueante(s) abiertas` : "");
                ok(false, "Decisión de criba", "Participamos, descartar o no viable (con motivo).");
                break;
            case "analisis":
                ok(this.conEmpresa.length > 0, `Renglones con empresa: ${this.conEmpresa.length} de ${this.partidas.length}`, "La primera empresa asignada es la principal.");
                ok(this.conProveedor.length > 0, `Renglones con proveedor: ${this.conProveedor.length} de ${this.conEmpresa.length || 0}`, "Al menos un proveedor en los renglones donde participamos.");
                ok(!this.bloqueantesAbiertas.length, "Sin incidencias bloqueantes", "");
                ok(this.expedientes.length > 0, "Expedientes generados", "Un expediente por empresa y una carta por proveedor.");
                break;
            case "preguntas":
                ok(this.expedientes.length > 0, `Expedientes: ${this.expedientes.length}`, "");
                ok(this.expedientes.some((e) => e.preguntas_count), `Preguntas capturadas: ${this.expedientes.reduce((s, e) => s + e.preguntas_count, 0)}`, "Se capturan dentro de cada expediente.");
                ok(!this.bloqueantesAbiertas.length, "Sin incidencias bloqueantes", "");
                break;
            case "costeo":
                ok(this.expedientes.every((e) => e.total_precio > 0), "Costeo capturado en todos los expedientes", "Costo y precio por renglón; la secundaria supera el margen de la principal.");
                ok(!this.bloqueantesAbiertas.length, "Sin incidencias bloqueantes", "");
                break;
            case "propuesta":
                ok(this.expedientes.every((e) => !e.bloqueantes_pendientes), "Sin bloqueantes en los expedientes", "Documentos obligatorios recibidos y vigentes.");
                ok(this.expedientes.every((e) => e.state === "publicado"), `Propuestas publicadas: ${this.expedientes.filter((e) => e.state === "publicado").length} de ${this.expedientes.length}`, "");
                ok(!this.bloqueantesAbiertas.length, "Sin incidencias bloqueantes", "");
                break;
            default:
                break;
        }
        return items;
    }

    get primaryAction() {
        const r = this.rec;
        if (!r) return null;
        switch (r.state) {
            case "detectado": return { label: "Participamos", icon: "fa-check", run: () => this.participar() };
            case "analisis": return { label: "Generar expedientes", icon: "fa-folder-open-o", run: () => this.generar() };
            case "preguntas": return { label: "Pasar a costeo", icon: "fa-arrow-right", run: () => this.avanzar() };
            case "costeo": return { label: "Pasar a propuesta", icon: "fa-arrow-right", run: () => this.avanzar() };
            case "propuesta": return { label: "Registrar fallo", icon: "fa-gavel", run: () => this.avanzar() };
            case "descartado": case "no_viable": return { label: "Reabrir con criba", icon: "fa-undo", run: () => this.cribar() };
            default: return null;
        }
    }

    // ------------------------------------------------------------------ acciones (métodos existentes)
    cribar() {
        return this.lp.call(MODELS.proc, "action_cribar", [this.rec.id], { reload: () => this.reload() });
    }

    async participar() {
        if (!await this.lp.confirm({ title: "Confirmar participación", body: `${this.rec.identificador} pasará a En análisis para asignar empresas y proveedores en sus renglones.`, confirmLabel: "Participamos" })) return;
        await this.lp.call(MODELS.proc, "action_pasar_a_analisis", [this.rec.id], { reload: () => this.reload() });
    }

    generar() {
        return this.lp.call(MODELS.proc, "action_generar_expedientes", [this.rec.id], { reload: () => this.reload() });
    }

    async avanzar() {
        const next = this.flow[this.currentIndex + 1];
        const nextLabel = next ? this.label(MODELS.proc, "state", next) : "";
        if (!await this.lp.confirm({ title: "Siguiente etapa", body: `${this.rec.identificador} pasará a «${nextLabel}».`, confirmLabel: "Avanzar" })) return;
        await this.lp.call(MODELS.proc, "action_avanzar", [this.rec.id], { reload: () => this.reload() });
    }

    openFicha() {
        this.lp.openRecord(MODELS.proc, this.rec.id);
    }

    editPartida(partida) {
        this.lp.openRecord(MODELS.partida, partida.id, { inDialog: true, onClose: () => this.reload() });
    }

    newPartida() {
        this.lp.openRecord(MODELS.partida, false, { inDialog: true, onClose: () => this.reload(), context: { default_procedimiento_id: this.rec.id } });
    }

    reabrirPartida(partida) {
        return this.lp.call(MODELS.partida, "action_reabrir", [partida.id], { reload: () => this.reload() });
    }

    propagar(what) {
        const ids = this.selectedIds;
        if (ids.length < 2) {
            this.lp.notification.add("Selecciona al menos dos renglones: la fuente y los que recibirán la copia.", { type: "warning" });
            return;
        }
        return this.lp.call(MODELS.partida, "action_propagar_" + what, ids, { reload: () => { this.state.selected = {}; return this.reload(); } });
    }

    resolverIncidencia(row, method) {
        return this.lp.call(MODELS.incidencia, method, [row.id], { reload: () => this.reload() });
    }

    openExpediente(exp) {
        this.lp.openExpediente(exp.id, exp.folio);
    }

    openCargas() {
        this.lp.openXmlAction("licitaciones_publicas.action_cargas", { additionalContext: { search_default_procedimiento_id: this.rec.id } });
    }

    // ------------------------------------------------------------------ renglones: filtros y selección
    get editable() {
        return this.rec && !["detectado", "descartado", "no_viable", "con_fallo"].includes(this.rec.state);
    }

    get filteredPartidas() {
        const q = this.state.query.trim().toLowerCase();
        return this.partidas.filter((p) => {
            if (this.state.filter === "sin_empresa" && p.company_ids.length) return false;
            if (this.state.filter === "con_empresa" && !p.company_ids.length) return false;
            if (this.state.filter === "descartadas" && p.participacion !== "descartada") return false;
            if (this.state.filter === "pendientes" && !p.cantidad_pendiente) return false;
            if (!q) return true;
            return [p.clave_cucop, p.partida_especifica, p.descripcion_detallada, p.descripcion_cucop, String(p.numero)].some((v) => (v || "").toString().toLowerCase().includes(q));
        });
    }

    get selectedIds() {
        return Object.keys(this.state.selected).filter((k) => this.state.selected[k]).map((k) => parseInt(k, 10));
    }

    toggleSelect(partida) {
        this.state.selected[partida.id] = !this.state.selected[partida.id];
    }

    toggleAll() {
        const all = this.filteredPartidas.every((p) => this.state.selected[p.id]);
        for (const p of this.filteredPartidas) this.state.selected[p.id] = !all;
    }

    companyChips(partida) {
        const principal = (m2o(partida.empresa_principal_id) || {}).id;
        return (partida.company_ids || []).map((id) => ({ id, name: this.companies[id] || `#${id}`, principal: id === principal }));
    }

    cantidadLabel(partida) {
        if (partida.cantidad_pendiente) return "Pendiente";
        const base = `${number(partida.cantidad, 2)} ${partida.unidad_medida || ""}`.trim();
        return partida.cantidad_min || partida.cantidad_max ? `${base} (${number(partida.cantidad_min, 0)}–${number(partida.cantidad_max, 0)})` : base;
    }

    // ------------------------------------------------------------------ fechas
    get timeline() {
        const r = this.rec;
        return this.fechas.map((f) => ({ ...f, value: r[f.field], tone: r[f.field] ? dateTone(r[f.field]) : "muted", when: fmtDateTime(r[f.field]), rel: relative(r[f.field]) }));
    }

    expedienteBloqueantes(exp) {
        return (exp.bloqueantes_pendientes || "").split("\n").filter(Boolean);
    }

    currency(exp) {
        return this.name(exp.currency_id) || "MXN";
    }
}
