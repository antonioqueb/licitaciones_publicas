/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { DateTime } from "luxon";
import { user } from "@web/core/user";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { serializeDate } from "@web/core/l10n/dates";
import { LpHeader } from "./header";
import { LpStepper, LpDropzone, LpEmpty } from "./components";
import { useLp } from "./nav";
import { loadLabels, label, loadCargasDelArchivo, MODELS, CARGA_FIELDS } from "./data";
import { CARGA_STATE_META, m2o, fmtDate, fmtDateTime, relative } from "./meta";

const ZONAS = ["America/Mexico_City", "America/Monterrey", "America/Chihuahua", "America/Hermosillo", "America/Tijuana", "America/Cancun", "America/Merida"];

/**
 * Importación guiada del Excel del portal en tres pasos: archivo, datos de la descarga y revisión.
 * El asistente nativo (`licitacion.carga.wizard`) sigue siendo quien valida, detecta duplicados por
 * SHA-256, previsualiza y confirma: aquí solo se crea con los datos capturados y se abre su resultado.
 */
export class LpCarga extends Component {
    static template = "licitaciones_publicas.Carga";
    static components = { LpHeader, LpStepper, LpDropzone, LpEmpty, DateTimeInput };
    static props = {};

    setup() {
        this.lp = useLp();
        this.MODELS = MODELS;
        this.cargaMeta = CARGA_STATE_META;
        this.zonas = ZONAS;
        this.name = (value) => (m2o(value) || {}).name || "";
        this.fmtDate = fmtDate;
        this.fmtDateTime = fmtDateTime;
        this.relative = relative;
        this.steps = [
            { key: "archivo", label: "Archivo", hint: "Excel exportado del portal" },
            { key: "datos", label: "Datos de la descarga", hint: "Fecha, alcance y zona horaria" },
            { key: "revisar", label: "Revisar y previsualizar", hint: "Nuevos, cambios y ausencias" },
        ];
        this.state = useState({
            step: "archivo", labels: null, file: null, analyzing: false, tipo: "", detalleBorrador: false, detectError: "",
            previas: [], recientes: [], fecha: DateTime.now().startOf("day"), origen: "comprasmx", alcance: "general",
            zona: "America/Mexico_City", busy: false, done: false, wizardId: null,
        });
        onWillStart(async () => {
            try {
                const [labels, recientes] = await Promise.all([
                    loadLabels(this.lp.orm),
                    this.lp.orm.searchRead(MODELS.carga, [], CARGA_FIELDS, { limit: 6, order: "id desc" }),
                ]);
                this.state.labels = labels;
                this.state.recientes = recientes;
            } catch (error) {
                this.lp.notify(error);
            }
        });
    }

    label(model, field, key) {
        return label(this.state.labels, model, field, key);
    }

    get stepIndex() {
        return this.steps.findIndex((s) => s.key === this.state.step);
    }

    get reached() {
        if (this.state.done) return 2;
        if (this.state.file) return 2;
        return 0;
    }

    get origenes() {
        const map = (this.state.labels && this.state.labels[MODELS.carga] && this.state.labels[MODELS.carga].origen_portal) || { comprasmx: "ComprasMX" };
        return Object.entries(map).map(([key, name]) => ({ key, name }));
    }

    get companies() {
        return (user.activeCompanies || []).map((c) => c.name);
    }

    get valid() {
        return !!this.state.file && !!this.state.fecha && !!(this.state.alcance || "").trim() && !!(this.state.zona || "").trim();
    }

    // ------------------------------------------------------------------ paso 1: archivo
    async onFile(file) {
        this.state.file = file;
        this.state.tipo = "";
        this.state.detalleBorrador = false;
        this.state.detectError = "";
        this.state.previas = [];
        this.state.done = false;
        this.state.wizardId = null;
        this.state.analyzing = true;
        try {
            const [previas, detected] = await Promise.all([
                loadCargasDelArchivo(this.lp.orm, file.sha256).catch(() => []),
                this.detect(file),
            ]);
            this.state.previas = previas;
            if (detected) {
                this.state.tipo = detected.tipo || "";
                this.state.detalleBorrador = !!detected.borrador;
            }
        } finally {
            this.state.analyzing = false;
        }
    }

    /** Pide al asistente nativo que detecte el tipo de archivo (mismo `onchange` que usa el formulario). */
    async detect(file) {
        try {
            const values = { archivo: file.base64, archivo_nombre: file.name, fecha_snapshot: serializeDate(this.state.fecha), origen_portal: this.state.origen, alcance: this.state.alcance, zona_horaria: this.state.zona };
            const result = await this.lp.orm.call(MODELS.cargaWizard, "onchange", [[], values, ["archivo", "archivo_nombre"], { tipo_detectado: {}, detalle_borrador: {} }]);
            const value = (result && result.value) || {};
            return { tipo: value.tipo_detectado || "", borrador: value.detalle_borrador };
        } catch (error) {
            this.state.detectError = (error && error.data && error.data.message) || (error && error.message) || "";
            return null;
        }
    }

    clearFile() {
        Object.assign(this.state, { file: null, tipo: "", detalleBorrador: false, detectError: "", previas: [], wizardId: null, done: false, step: "archivo" });
    }

    // ------------------------------------------------------------------ navegación
    go(step) {
        if (step !== "archivo" && !this.state.file) return;
        this.state.step = step;
    }

    next() {
        if (this.state.step === "archivo" && this.state.file) this.state.step = "datos";
        else if (this.state.step === "datos" && this.valid) this.state.step = "revisar";
    }

    back() {
        if (this.state.step === "datos") this.state.step = "archivo";
        else if (this.state.step === "revisar") this.state.step = "datos";
    }

    onFecha(value) {
        this.state.fecha = value || null;
    }

    // ------------------------------------------------------------------ paso 3: asistente nativo
    async ensureWizard() {
        if (this.state.wizardId) return this.state.wizardId;
        const [id] = await this.lp.orm.create(MODELS.cargaWizard, [{
            archivo: this.state.file.base64, archivo_nombre: this.state.file.name, fecha_snapshot: serializeDate(this.state.fecha),
            origen_portal: this.state.origen, alcance: (this.state.alcance || "").trim(), zona_horaria: (this.state.zona || "").trim(),
        }]);
        this.state.wizardId = id;
        return id;
    }

    /** Ejecuta un método del asistente nativo y abre lo que devuelva (previsualización, asignación, formulario). */
    async runWizard(method) {
        if (!this.valid || this.state.busy) return;
        this.state.busy = true;
        try {
            const id = await this.ensureWizard();
            const result = await this.lp.orm.call(MODELS.cargaWizard, method, [[id]]);
            if (result && typeof result === "object" && result.type) {
                await this.lp.action.doAction(result, { onClose: () => this.afterWizard() });
            } else {
                await this.afterWizard();
            }
        } catch (error) {
            this.lp.notify(error);
        } finally {
            this.state.busy = false;
        }
    }

    async afterWizard() {
        this.state.done = true;
        try {
            this.state.recientes = await this.lp.orm.searchRead(MODELS.carga, [], CARGA_FIELDS, { limit: 6, order: "id desc" });
        } catch {
            // la lista de recientes es informativa
        }
    }

    previsualizar() { return this.runWizard("action_preview"); }
    abrirExistente() { return this.runWizard("action_open_existing"); }
    forzar() { return this.runWizard("action_force"); }

    otra() {
        this.clearFile();
        this.state.wizardId = null;
    }

    openCarga(row) {
        this.lp.openRecord(MODELS.carga, row.id);
    }

    openHistorial() {
        this.lp.openXmlAction("licitaciones_publicas.action_cargas", { clearBreadcrumbs: true });
    }

    openTipos() {
        this.lp.openXmlAction("licitaciones_publicas.action_tipo_archivo", { clearBreadcrumbs: true });
    }
}
