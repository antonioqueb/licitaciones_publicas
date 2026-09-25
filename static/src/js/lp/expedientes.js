/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { useDebounced } from "@web/core/utils/timing";
import { LpHeader } from "./header";
import { LpEmpty } from "./components";
import { useLp } from "./nav";
import { loadExpedientes, loadLabels, label, MODELS } from "./data";
import { EXP_FLOW, EXP_META, m2o, relative, money, pct } from "./meta";

const PAGE = 24;

/** Lista de expedientes por empresa con filtro por etapa de armado. */
export class LpExpedientes extends Component {
    static template = "licitaciones_publicas.Expedientes";
    static components = { LpHeader, LpEmpty };
    static props = { filters: { type: Object, optional: true } };

    setup() {
        this.lp = useLp();
        this.flow = EXP_FLOW;
        this.meta = EXP_META;
        this.MODELS = MODELS;
        this.name = (value) => (m2o(value) || {}).name || "";
        this.relative = relative;
        this.money = money;
        this.pct = pct;
        const f = this.props.filters || {};
        this.state = useState({ loading: true, labels: null, records: [], total: 0, counts: {}, query: f.query || "", stateKey: f.state || "", offset: 0 });
        this.debounced = useDebounced(() => this.load(0), 300);
        onWillStart(async () => {
            this.state.labels = await loadLabels(this.lp.orm).catch((e) => (this.lp.notify(e), null));
            await this.load(0);
        });
    }

    async load(offset = this.state.offset) {
        this.state.loading = true;
        try {
            const data = await loadExpedientes(this.lp.orm, { query: this.state.query, state: this.state.stateKey, offset, limit: PAGE });
            Object.assign(this.state, { records: data.records, total: data.total, counts: data.counts, offset });
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
        return key ? this.state.counts[key] || 0 : Object.values(this.state.counts).reduce((a, b) => a + b, 0);
    }

    setState(key) {
        this.state.stateKey = key;
        this.load(0);
    }

    onQuery(ev) {
        this.state.query = ev.target.value;
        this.debounced();
    }

    get pageFrom() { return this.state.total ? this.state.offset + 1 : 0; }
    get pageTo() { return Math.min(this.state.total, this.state.offset + this.state.records.length); }
    prev() { if (this.state.offset > 0) this.load(Math.max(0, this.state.offset - PAGE)); }
    next() { if (this.pageTo < this.state.total) this.load(this.state.offset + PAGE); }

    bloqueantes(row) {
        return (row.bloqueantes_pendientes || "").split("\n").filter(Boolean);
    }

    currency(row) {
        return this.name(row.currency_id) || "MXN";
    }

    open(row) {
        this.lp.openExpediente(row.id, row.folio);
    }

    openProc(row) {
        const proc = m2o(row.procedimiento_id);
        if (proc) this.lp.openProcedimiento(proc.id, proc.name);
    }

    openClassic() {
        this.lp.openXmlAction("licitaciones_publicas.action_expedientes", { clearBreadcrumbs: true });
    }
}
