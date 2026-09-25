/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { useDebounced } from "@web/core/utils/timing";
import { user } from "@web/core/user";
import { LpHeader } from "./header";
import { LpEmpty, LpAvatar } from "./components";
import { useLp } from "./nav";
import { loadProcedimientos, loadLabels, label, MODELS } from "./data";
import { PROC_FLOW, PROC_META, JUNTA_META, m2o, fmtDateTime, relative } from "./meta";

const PAGE = 24;

/** Lista de procedimientos como tarjetas, con filtros por etapa, semáforo, entidad y texto. */
export class LpProcedimientos extends Component {
    static template = "licitaciones_publicas.Procedimientos";
    static components = { LpHeader, LpEmpty, LpAvatar };
    static props = { filters: { type: Object, optional: true } };

    setup() {
        this.lp = useLp();
        this.flow = PROC_FLOW;
        this.meta = PROC_META;
        this.juntaMeta = JUNTA_META;
        this.MODELS = MODELS;
        this.m2o = m2o;
        this.name = (value) => (m2o(value) || {}).name || "";
        this.fmtDateTime = fmtDateTime;
        this.relative = relative;
        this.companies = Object.fromEntries((user.allowedCompanies || []).map((c) => [c.id, c.name]));
        const f = this.props.filters || {};
        this.state = useState({
            loading: true, labels: null, records: [], total: 0, counts: {}, entidades: [],
            query: f.query || "", stateKey: f.state === undefined ? "__relevantes" : f.state, entidad: f.entidad || 0,
            junta: f.junta || "", mine: !!f.mine, ausentes: !!f.ausentes, offset: 0, layout: "cards",
        });
        this.debounced = useDebounced(() => this.load(0), 300);
        onWillStart(async () => {
            this.state.labels = await loadLabels(this.lp.orm).catch((e) => (this.lp.notify(e), null));
            await this.load(0);
        });
    }

    async load(offset = this.state.offset) {
        this.state.loading = true;
        try {
            const data = await loadProcedimientos(this.lp.orm, {
                query: this.state.query, state: this.state.stateKey, entidad: this.state.entidad, junta: this.state.junta,
                mine: this.state.mine, ausentes: this.state.ausentes, offset, limit: PAGE, uid: user.userId,
            });
            Object.assign(this.state, { records: data.records, total: data.total, counts: data.counts, entidades: data.entidades, offset });
        } catch (error) {
            this.lp.notify(error);
        } finally {
            this.state.loading = false;
        }
    }

    label(model, field, key) {
        return label(this.state.labels, model, field, key);
    }

    count(key) {
        if (key === "__relevantes") return this.flow.reduce((sum, k) => sum + (this.state.counts[k] || 0), 0) - (this.state.counts.con_fallo || 0);
        if (key === "") return Object.values(this.state.counts).reduce((a, b) => a + b, 0);
        return this.state.counts[key] || 0;
    }

    setState(key) {
        this.state.stateKey = key;
        this.load(0);
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        this.debounced();
    }

    onEntidad(ev) {
        this.state.entidad = parseInt(ev.target.value, 10) || 0;
        this.load(0);
    }

    setJunta(key) {
        this.state.junta = this.state.junta === key ? "" : key;
        this.load(0);
    }

    toggle(flag) {
        this.state[flag] = !this.state[flag];
        this.load(0);
    }

    clear() {
        Object.assign(this.state, { query: "", stateKey: "__relevantes", entidad: 0, junta: "", mine: false, ausentes: false });
        this.load(0);
    }

    get hasFilters() {
        return this.state.query || this.state.stateKey !== "__relevantes" || this.state.entidad || this.state.junta || this.state.mine || this.state.ausentes;
    }

    get pageFrom() { return this.state.total ? this.state.offset + 1 : 0; }
    get pageTo() { return Math.min(this.state.total, this.state.offset + this.state.records.length); }
    prev() { if (this.state.offset > 0) this.load(Math.max(0, this.state.offset - PAGE)); }
    next() { if (this.pageTo < this.state.total) this.load(this.state.offset + PAGE); }

    companyNames(ids) {
        return (ids || []).map((id) => this.companies[id] || `#${id}`);
    }

    open(row) {
        this.lp.openProcedimiento(row.id, row.identificador);
    }

    cribar(row) {
        this.lp.call(MODELS.proc, "action_cribar", [row.id], { reload: () => this.load() });
    }

    openClassic() {
        this.lp.openXmlAction("licitaciones_publicas.action_procedimientos", { clearBreadcrumbs: true });
    }
}
