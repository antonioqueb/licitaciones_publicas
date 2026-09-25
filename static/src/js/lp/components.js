/** @odoo-module **/
/**
 * Componentes visuales compartidos del Centro de Licitaciones: paso a paso, zona de archivos, tarjetas
 * de indicador, avatares y estados vacíos. No conocen los modelos: reciben datos ya preparados.
 */
import { Component, useRef, useState } from "@odoo/owl";
import { initials } from "./meta";

/** Barra de etapas. `steps`: [{key, label, hint?, icon?}], `current`: key activa, `reached`: índice alcanzado. */
export class LpStepper extends Component {
    static template = "licitaciones_publicas.LpStepper";
    static props = {
        steps: Array,
        current: { type: [String, Boolean], optional: true },
        reached: { type: Number, optional: true },
        terminal: { type: [String, Boolean], optional: true },
        onSelect: { type: Function, optional: true },
        compact: { type: Boolean, optional: true },
    };

    status(index) {
        const current = this.props.steps.findIndex((s) => s.key === this.props.current);
        const reached = this.props.reached ?? current;
        if (this.props.terminal) return index <= reached ? "done" : "off";
        if (index < current) return "done";
        if (index === current) return "current";
        return index <= reached ? "reachable" : "off";
    }

    select(step, index) {
        if (this.props.onSelect && this.status(index) !== "off") this.props.onSelect(step.key, index);
    }
}

/** Zona de arrastre para un archivo. Devuelve {name, size, base64, sha256} en `onFile`. */
export class LpDropzone extends Component {
    static template = "licitaciones_publicas.LpDropzone";
    static props = {
        accept: { type: String, optional: true },
        file: { type: [Object, { value: null }], optional: true },
        busy: { type: Boolean, optional: true },
        onFile: Function,
        onClear: { type: Function, optional: true },
    };

    setup() {
        this.input = useRef("input");
        this.state = useState({ over: false, error: "" });
    }

    open() {
        this.input.el?.click();
    }

    onDragOver(ev) {
        ev.preventDefault();
        this.state.over = true;
    }

    onDragLeave() {
        this.state.over = false;
    }

    onDrop(ev) {
        ev.preventDefault();
        this.state.over = false;
        const file = ev.dataTransfer?.files?.[0];
        if (file) this.read(file);
    }

    onChange(ev) {
        const file = ev.target.files?.[0];
        if (file) this.read(file);
        ev.target.value = "";
    }

    async read(file) {
        this.state.error = "";
        if (this.props.accept && !file.name.toLowerCase().endsWith(this.props.accept)) {
            this.state.error = `Solo se aceptan archivos ${this.props.accept}.`;
            return;
        }
        const buffer = await file.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = "";
        const chunk = 0x8000;
        for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
        const base64 = btoa(binary);
        let sha256 = "";
        try {
            const digest = await crypto.subtle.digest("SHA-256", buffer);
            sha256 = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
        } catch {
            sha256 = "";
        }
        this.props.onFile({ name: file.name, size: file.size, base64, sha256 });
    }

    get sizeLabel() {
        const size = this.props.file?.size || 0;
        return size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;
    }
}

/** Avatar con iniciales para responsables y empresas. */
export class LpAvatar extends Component {
    static template = "licitaciones_publicas.LpAvatar";
    static props = { name: { type: String, optional: true }, tone: { type: String, optional: true }, small: { type: Boolean, optional: true } };
    get initials() {
        return initials(this.props.name);
    }
}

/** Indicador con número, etiqueta y tono; opcionalmente clicable. */
export class LpKpi extends Component {
    static template = "licitaciones_publicas.LpKpi";
    static props = {
        value: { type: [Number, String], optional: true },
        label: String,
        hint: { type: String, optional: true },
        tone: { type: String, optional: true },
        icon: { type: String, optional: true },
        onClick: { type: Function, optional: true },
    };
}

/** Estado vacío con icono, título, texto y acción opcional. */
export class LpEmpty extends Component {
    static template = "licitaciones_publicas.LpEmpty";
    static props = {
        icon: { type: String, optional: true },
        title: String,
        text: { type: String, optional: true },
        actionLabel: { type: String, optional: true },
        onAction: { type: Function, optional: true },
        compact: { type: Boolean, optional: true },
    };
}
