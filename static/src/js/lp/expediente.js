/** @odoo-module **/
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { LpHeader } from "./header";
import { LpStepper, LpEmpty } from "./components";
import { useLp } from "./nav";
import { loadExpediente, loadLabels, label, MODELS } from "./data";
import { EXP_FLOW, EXP_META, DOC_STATE_META, PREGUNTA_META, CARTA_META, m2o, fmtDateTime, fmtDate, relative, dateTone, money, number, pct } from "./meta";

/**
 * Armado guiado de un expediente. El estado y los bloqueantes los calcula el servidor; aquí se ordenan
 * en una lista de verificación y se abren las capturas nativas (pregunta, costeo, documento) en diálogo.
 */
export class LpExpediente extends Component {
    static template = "licitaciones_publicas.Expediente";
    static components = { LpHeader, LpStepper, LpEmpty };
    static props = { recordId: { type: [Number, Boolean, { value: null }], optional: true } };

    setup() {
        this.lp = useLp();
        this.flow = EXP_FLOW;
        this.meta = EXP_META;
        this.docMeta = DOC_STATE_META;
        this.pregMeta = PREGUNTA_META;
        this.cartaMeta = CARTA_META;
        this.MODELS = MODELS;
        this.name = (value) => (m2o(value) || {}).name || "";
        this.fmtDateTime = fmtDateTime;
        this.fmtDate = fmtDate;
        this.relative = relative;
        this.dateTone = dateTone;
        this.money = money;
        this.number = number;
        this.pct = pct;
        this.state = useState({ loading: true, labels: null, data: null, tab: "preguntas" });
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
            const [labels, data] = await Promise.all([loadLabels(this.lp.orm), loadExpediente(this.lp.orm, id)]);
            this.state.labels = labels;
            this.state.data = data;
            if (data) {
                if (!this.state.tabTouched) this.state.tab = this.tabFor(data);
                if (this.env.config && this.env.config.setDisplayName) this.env.config.setDisplayName(data.record.folio);
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

    setTab(tab) {
        this.state.tab = tab;
        this.state.tabTouched = true;
    }

    /** Pestaña sugerida según la etapa del procedimiento: preguntas → costeo → documentos. */
    tabFor(data) {
        const state = data.proc && data.proc.state;
        if (state === "costeo") return "costeo";
        if (state === "propuesta" || data.record.state === "listo") return "documentos";
        return "preguntas";
    }

    label(model, field, key) {
        return label(this.state.labels, model, field, key);
    }

    get rec() { return this.state.data ? this.state.data.record : null; }
    get proc() { return this.state.data ? this.state.data.proc : null; }
    get preguntas() { return this.state.data ? this.state.data.preguntas : []; }
    get costeo() { return this.state.data ? this.state.data.costeo : []; }
    get documentos() { return this.state.data ? this.state.data.documentos : []; }
    get cartas() { return this.state.data ? this.state.data.cartas : []; }
    get partidas() { return this.state.data ? this.state.data.partidas : []; }
    get currency() { return this.name(this.rec.currency_id) || "MXN"; }

    get steps() {
        return this.flow.map((key) => ({ key, label: this.label(MODELS.exp, "state", key), icon: this.meta[key].icon }));
    }

    get currentIndex() {
        return this.flow.indexOf(this.rec.state);
    }

    get bloqueantes() {
        return (this.rec.bloqueantes_pendientes || "").split("\n").filter(Boolean);
    }

    get docsProveedor() { return this.documentos.filter((d) => d.origen === "proveedor"); }
    get docsPropios() { return this.documentos.filter((d) => d.origen === "propio"); }

    docCounts(list) {
        const counts = { total: list.length, recibido: 0, pendiente: 0, vencido: 0 };
        for (const d of list) {
            if (d.state === "recibido") counts.recibido++;
            else if (d.state === "vencido") counts.vencido++;
            else if (d.state !== "no_aplica") counts.pendiente++;
        }
        return counts;
    }

    get costeadas() {
        const ids = new Set(this.costeo.map((c) => (m2o(c.partida_id) || {}).id));
        return this.partidas.filter((p) => ids.has(p.id)).length;
    }

    get checklist() {
        const r = this.rec;
        const items = [];
        const ok = (done, text, hint) => items.push({ done, text, hint });
        if (r.state === "borrador") {
            ok(false, "Comenzar el armado", "Habilita la captura de preguntas, costeo y documentos.");
            return items;
        }
        ok(this.preguntas.length > 0, `Preguntas para la junta: ${this.preguntas.length}`, "Opcional, pero conviene tenerlas antes del límite de preguntas.");
        ok(this.partidas.length > 0 && this.costeadas === this.partidas.length, `Costeo: ${this.costeadas} de ${this.partidas.length} renglones`, "Costo y precio por renglón de esta empresa.");
        for (const b of this.bloqueantes) ok(false, b, "Bloqueante: impide marcar listo y publicar.");
        if (!this.bloqueantes.length) ok(true, "Sin bloqueantes pendientes", "");
        const enviadas = this.cartas.filter((c) => c.state !== "borrador").length;
        if (this.cartas.length) ok(enviadas === this.cartas.length, `Cartas de apoyo enviadas: ${enviadas} de ${this.cartas.length}`, "Se envían por correo al proveedor desde la pestaña Cartas.");
        return items;
    }

    get primaryAction() {
        switch (this.rec.state) {
            case "borrador": return { label: "Comenzar armado", icon: "fa-play", run: () => this.run("action_armar") };
            case "en_armado": return { label: "Marcar listo", icon: "fa-check-square-o", run: () => this.run("action_listo"), disabled: this.bloqueantes.length > 0 };
            case "listo": return { label: "Publicar propuesta", icon: "fa-flag-checkered", run: () => this.publicar(), disabled: this.bloqueantes.length > 0 };
            default: return null;
        }
    }

    // ------------------------------------------------------------------ acciones existentes
    run(method) {
        return this.lp.call(MODELS.exp, method, [this.rec.id], { reload: () => this.reload() });
    }

    async publicar() {
        if (!await this.lp.confirm({ title: "Publicar propuesta", body: `${this.rec.folio} quedará como Publicado. Este estado es interno: no publica en ComprasMX.`, confirmLabel: "Publicar" })) return;
        await this.run("action_publicar");
    }

    openFicha() {
        this.lp.openRecord(MODELS.exp, this.rec.id);
    }

    openProc() {
        const proc = m2o(this.rec.procedimiento_id);
        this.lp.openProcedimiento(proc.id, proc.name);
    }

    get editable() {
        return this.rec && this.rec.state !== "publicado";
    }

    newPregunta() {
        this.lp.openRecord(MODELS.pregunta, false, { inDialog: true, onClose: () => this.reload(), context: { default_expediente_id: this.rec.id } });
    }

    editPregunta(row) {
        this.lp.openRecord(MODELS.pregunta, row.id, { inDialog: true, onClose: () => this.reload() });
    }

    newCosteo(partida) {
        this.lp.openRecord(MODELS.costeo, false, { inDialog: true, onClose: () => this.reload(), context: { default_expediente_id: this.rec.id, default_partida_id: partida ? partida.id : false } });
    }

    editCosteo(row) {
        this.lp.openRecord(MODELS.costeo, row.id, { inDialog: true, onClose: () => this.reload() });
    }

    newDoc(origen) {
        this.lp.openRecord(MODELS.doc, false, { inDialog: true, onClose: () => this.reload(), context: { default_expediente_id: this.rec.id, default_tipo: origen === "proveedor" ? "prov_ficha" : "propio_otro" } });
    }

    editDoc(row) {
        this.lp.openRecord(MODELS.doc, row.id, { inDialog: true, onClose: () => this.reload() });
    }

    editCarta(row) {
        this.lp.openRecord(MODELS.carta, row.id, { inDialog: true, onClose: () => this.reload() });
    }

    cartaPdf(row) {
        return this.lp.call(MODELS.carta, "action_print_carta", [row.id], {});
    }

    async cartaEnviar(row) {
        if (!await this.lp.confirm({ title: "Enviar carta de apoyo", body: `Se colocará en la cola de correo la carta ${row.folio} para ${this.name(row.partner_id)}.`, confirmLabel: "Enviar" })) return;
        await this.lp.call(MODELS.carta, "action_enviar", [row.id], { reload: () => this.reload() });
    }

    cartaRespondida(row) {
        return this.lp.call(MODELS.carta, "action_respondida", [row.id], { reload: () => this.reload() });
    }

    cartasZip() {
        return this.lp.call(MODELS.exp, "action_print_cartas_zip", [this.rec.id], {});
    }

    report(xmlid) {
        return this.lp.openXmlAction("licitaciones_publicas." + xmlid, { additionalContext: { active_ids: [this.rec.id], active_id: this.rec.id, active_model: MODELS.exp } });
    }

    // ------------------------------------------------------------------ presentación
    partidaOf(row) {
        return this.name(row.partida_id);
    }

    partidaCosteo(partida) {
        return this.costeo.find((c) => (m2o(c.partida_id) || {}).id === partida.id) || null;
    }

    docTone(doc) {
        if (doc.state === "recibido" && doc.fecha_vencimiento && dateTone(doc.fecha_vencimiento) === "danger") return "danger";
        return this.docMeta[doc.state].tone;
    }
}
