/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { user } from "@web/core/user";
import { DateTime } from "luxon";
import { LpHeader } from "./header";
import { LpKpi, LpEmpty, LpAvatar } from "./components";
import { useLp } from "./nav";
import { loadInicio, loadLabels, label, MODELS } from "./data";
import { PROC_FLOW, PROC_META, JUNTA_META, EXP_META, CARGA_STATE_META, INCIDENCIA_META, m2o, fmtDateTime, fmtDate, relative, dateTone, toDateTime, tone } from "./meta";

/** Tablero de inicio: qué requiere decisión hoy, agenda de la semana y accesos guiados. */
export class LpInicio extends Component {
    static template = "licitaciones_publicas.Inicio";
    static components = { LpHeader, LpKpi, LpEmpty, LpAvatar };
    static props = {};

    setup() {
        this.lp = useLp();
        this.user = user;
        this.flow = PROC_FLOW;
        this.meta = PROC_META;
        this.juntaMeta = JUNTA_META;
        this.expMeta = EXP_META;
        this.cargaMeta = CARGA_STATE_META;
        this.incMeta = INCIDENCIA_META;
        this.m2o = m2o;
        this.name = (value) => (m2o(value) || {}).name || "";
        this.bloqueantes = (row) => (row.bloqueantes_pendientes || "").split("\n").filter(Boolean).length;
        this.fmtDateTime = fmtDateTime;
        this.fmtDate = fmtDate;
        this.relative = relative;
        this.dateTone = dateTone;
        this.tone = tone;
        this.MODELS = MODELS;
        this.state = useState({ loading: true, data: null, labels: null, guide: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const [labels, data] = await Promise.all([loadLabels(this.lp.orm), loadInicio(this.lp.orm)]);
            this.state.labels = labels;
            this.state.data = data;
        } catch (error) {
            this.lp.notify(error);
        } finally {
            this.state.loading = false;
        }
    }

    label(model, field, key) {
        return label(this.state.labels, model, field, key);
    }

    get greeting() {
        const hour = DateTime.now().hour;
        const word = hour < 12 ? "Buenos días" : hour < 19 ? "Buenas tardes" : "Buenas noches";
        return `${word}, ${(user.name || "").split(" ")[0]}`;
    }

    get today() {
        return DateTime.now().setLocale("es").toFormat("cccc d 'de' LLLL");
    }

    get company() {
        return user.activeCompany?.name || "";
    }

    get enCurso() {
        const counts = this.state.data?.counts || {};
        return ["analisis", "preguntas", "costeo", "propuesta"].reduce((sum, key) => sum + (counts[key] || 0), 0);
    }

    count(key) {
        return (this.state.data?.counts || {})[key] || 0;
    }

    /** Agenda de la semana agrupada por día, con el tono de urgencia de cada evento. */
    get agendaDays() {
        const days = [];
        for (const row of this.state.data?.agenda || []) {
            const dt = toDateTime(row.fecha);
            const key = dt.toISODate();
            let day = days.find((d) => d.key === key);
            if (!day) {
                day = { key, label: dt.setLocale("es").toFormat("cccc d"), relative: dt.startOf("day").toRelativeCalendar({ locale: "es" }), items: [] };
                days.push(day);
            }
            day.items.push({ ...row, time: dt.toFormat("HH:mm"), tone: dateTone(row.fecha), proc: m2o(row.procedimiento_id) || { id: null, name: "" } });
        }
        return days;
    }

    openProc(row) {
        const proc = row.identificador ? { id: row.id, name: row.identificador } : m2o(row.procedimiento_id);
        this.lp.openProcedimiento(proc.id, proc.name);
    }

    openExp(row) {
        this.lp.openExpediente(row.id, row.folio);
    }

    openIncidencia(row) {
        this.lp.openRecord(MODELS.incidencia, row.id, { inDialog: true, onClose: () => this.load() });
    }

    openCarga(row) {
        this.lp.openRecord(MODELS.carga, row.id);
    }

    cribar(row) {
        this.lp.call(MODELS.proc, "action_cribar", [row.id], { reload: () => this.load() });
    }
}
