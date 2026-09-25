/* Prueba de humo sin Odoo del Centro de Licitaciones: monta cada espacio guiado con el OWL de Odoo 19,
 * luxon y servicios simulados (orm, action, dialog, notification) y comprueba que renderiza y reacciona
 * a las interacciones básicas sin errores. No sustituye la revisión en una instancia.
 *
 * Uso: NODE_PATH=<dir con jsdom y luxon> OWL_PATH=<owl.js de Odoo 19> node tests/lp_smoke.cjs
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const luxon = require('luxon');

const SRC = path.join(__dirname, '../static/src');
const read = (file) => fs.readFileSync(file, 'utf8');
const strip = (source) => source
    .replace(/^import [^;]*;$/gm, '')
    .replace(/^export (class|function|const|async function) /gm, '$1 ')
    .replace(/^export function /gm, 'function ')
    .replace(/^const ([A-Z_]+) = /gm, 'var $1 = ');

const tick = (ms = 25) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
    const dom = new JSDOM('<!doctype html><html><body></body></html>', { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://licitaciones.example.test/' });
    const w = dom.window;
    w.luxon = luxon;
    w.eval(read(process.env.OWL_PATH));

    // plantillas del módulo en un solo <templates>
    let inner = '';
    for (const file of fs.readdirSync(path.join(SRC, 'xml')).filter((f) => f.startsWith('lp_'))) {
        inner += read(path.join(SRC, 'xml', file)).replace(/<\?xml[^>]*\?>/, '').replace(/^[\s\S]*?<templates[^>]*>/, '').replace(/<\/templates>\s*$/, '');
    }
    const templates = `<templates xml:space="preserve">${inner}</templates>`;

    // ------------------------------------------------------------ datos de ejemplo
    const now = luxon.DateTime.utc();
    const sql = (dt) => dt.toFormat('yyyy-MM-dd HH:mm:ss');
    const proc = (id, extra) => ({
        id, identificador: `LA-06-TCL-0000${id}-N-1-2026`, nombre_publicado: `Adquisición de material de curación ${id}`, state: 'detectado', junta_class: 'urgente',
        fecha_junta_aclaraciones: sql(now.plus({ hours: 30 })), fecha_limite_preguntas: sql(now.plus({ hours: 20 })), fecha_entrega_muestras: false,
        fecha_apertura: sql(now.plus({ days: 6 })), fecha_fallo: sql(now.plus({ days: 12 })), fecha_fallo_original: false, fallo_diferido: false,
        unidad_compradora_id: [5, 'IMSS Zacatecas'], entidad_id: [32, 'Zacatecas'], tipo_contratacion_id: [2, 'Adquisiciones'], estatus_portal_id: [1, 'Vigente'],
        user_id: [2, 'Ana Prueba'], company_ids: [1, 2], sigue_apareciendo: true, fecha_ya_no_aparece: false, renglones_count: 3, renglones_con_empresa_count: 1,
        renglones_descartados_count: 0, incidencias_abiertas_count: 1, motivo_descarte_id: false, nota_criba: false, reapertura_habilitada: false,
        codigo_expediente: 'E-2026-12', tipo_procedimiento: 'LA', caracter: 'N', ejercicio: '2026', tipo_procedimiento_id: [1, 'LA'], caracter_procedimiento_id: [1, 'N'],
        write_date: sql(now.minus({ hours: 3 })), active: true, ...extra,
    });
    const procs = [proc(1), proc(2, { state: 'analisis', junta_class: 'normal' }), proc(3, { state: 'propuesta', junta_class: 'vencida' }), proc(4, { state: 'descartado', motivo_descarte_id: [1, 'Sin giro'], nota_criba: 'Fuera de alcance' })];
    const partidas = [
        { id: 11, numero: 1, partida_especifica: '25301', clave_cucop: '25301001', descripcion_cucop: 'Gasas', descripcion_detallada: 'Gasa estéril 10x10', unidad_medida: 'PIEZA', cantidad: 500, cantidad_pendiente: false, cantidad_min: 0, cantidad_max: 0, participacion: 'participamos', motivo_descarte_id: false, company_ids: [1, 2], empresa_principal_id: [1, 'BioTecZac'], sigue_apareciendo: true, importada: true },
        { id: 12, numero: 2, partida_especifica: '25301', clave_cucop: '25301002', descripcion_cucop: '', descripcion_detallada: 'Venda elástica 5 cm', unidad_medida: 'PIEZA', cantidad: 0, cantidad_pendiente: true, cantidad_min: 10, cantidad_max: 100, participacion: 'sin_decidir', motivo_descarte_id: false, company_ids: [], empresa_principal_id: false, sigue_apareciendo: false, importada: true },
        { id: 13, numero: 3, partida_especifica: '25401', clave_cucop: '25401001', descripcion_cucop: '', descripcion_detallada: 'Guante de látex', unidad_medida: 'CAJA', cantidad: 40, cantidad_pendiente: false, cantidad_min: 0, cantidad_max: 0, participacion: 'descartada', motivo_descarte_id: [1, 'Sin giro'], company_ids: [], empresa_principal_id: false, sigue_apareciendo: true, importada: true },
    ];
    const expedientes = [
        { id: 21, folio: 'EXP/2026/0001', procedimiento_id: [2, procs[1].identificador], company_id: [1, 'BioTecZac'], state: 'en_armado', partidas_count: 2, proveedores_count: 1, preguntas_count: 1, total_costo: 1000, total_precio: 1500, margen_bruto: 500, margen_pct: 33.33, currency_id: [33, 'MXN'], bloqueantes_pendientes: 'Pago de bases\nIncidencias bloqueantes abiertas', write_date: sql(now.minus({ hours: 1 })), partida_ids: [11, 12], proveedor_ids: [7] },
        { id: 22, folio: 'EXP/2026/0002', procedimiento_id: [2, procs[1].identificador], company_id: [2, 'Valma'], state: 'listo', partidas_count: 1, proveedores_count: 0, preguntas_count: 0, total_costo: 0, total_precio: 0, margen_bruto: 0, margen_pct: 0, currency_id: [33, 'MXN'], bloqueantes_pendientes: '', write_date: sql(now.minus({ days: 1 })), partida_ids: [11], proveedor_ids: [] },
    ];
    const incidencias = [{ id: 31, procedimiento_id: [1, procs[0].identificador], partida_id: false, carga_id: [41, 'listado.xlsx'], origen: 'procedimiento', campo: 'fecha_apertura', valor_esperado: '2026-10-01', valor_encontrado: '2026-10-03', severidad: 'bloqueante', state: 'abierta', create_date: sql(now.minus({ hours: 5 })), es_valor_no_reconocido: false, identificador_observado: false }];
    const cargas = [{ id: 41, archivo_nombre: 'listado-2026-09-25.xlsx', fecha_snapshot: '2026-09-25', tipo_detectado: 'listado', subtipo_detectado: 'listado', alcance: 'general', registros: 117, state: 'confirmada', resumen: 'Nuevos: 3 · Cambios: 1 · Sin cambios: 100 · Ya no aparecen: 2', user_id: [2, 'Ana Prueba'], procesado_el: sql(now.minus({ hours: 6 })), reimportacion_forzada: false, procedimiento_id: false }];
    const fechas = [
        { id: 101, name: procs[0].identificador, procedimiento_id: [1, procs[0].identificador], tipo: 'junta', fecha: sql(now.plus({ hours: 30 })), state: 'detectado', user_id: [2, 'Ana Prueba'] },
        { id: 102, name: procs[1].identificador, procedimiento_id: [2, procs[1].identificador], tipo: 'apertura', fecha: sql(now.plus({ days: 3 })), state: 'analisis', user_id: [2, 'Ana Prueba'] },
    ];
    const preguntas = [{ id: 51, sequence: 10, partida_id: [11, '25301001'], texto: '¿Se acepta muestra equivalente?', autor_id: [2, 'Ana Prueba'], fecha: sql(now.minus({ hours: 2 })), state: 'borrador', respuesta_portal: false }];
    const costeo = [{ id: 61, partida_id: [11, '25301001'], proveedor_id: [7, 'Proveedor Uno'], cantidad: 500, costo_unitario: 2, precio_unitario: 3, total_costo: 1000, total_precio: 1500, margen_pct: 33.33, recargo_secundaria_pct: 0, es_secundaria: false }];
    const documentos = [
        { id: 71, tipo: 'prov_ficha', origen: 'proveedor', partner_id: [7, 'Proveedor Uno'], partida_id: [11, '25301001'], state: 'recibido', fecha_recepcion: '2026-09-20', fecha_vencimiento: '2027-01-01', monto: 0, bloqueante: true, archivo_nombre: 'ficha.pdf', nota: false },
        { id: 72, tipo: 'propio_pago_bases', origen: 'propio', partner_id: false, partida_id: false, state: 'pendiente', fecha_recepcion: false, fecha_vencimiento: false, monto: 1200, bloqueante: true, archivo_nombre: false, nota: false },
    ];
    const cartas = [{ id: 81, folio: 'CARTA/2026/0001', partner_id: [7, 'Proveedor Uno'], state: 'borrador', fecha_envio: false, fecha_respuesta: false, partida_ids: [11] }];
    const selections = {
        'licitacion.procedimiento': { state: [['detectado', 'Detectado'], ['analisis', 'En análisis'], ['preguntas', 'En preguntas'], ['costeo', 'Costeo'], ['propuesta', 'Propuesta'], ['con_fallo', 'Con fallo'], ['descartado', 'Descartado'], ['no_viable', 'No viable']], junta_class: [['sin_fecha', 'Sin fecha'], ['normal', 'Próxima'], ['urgente', 'En 72 h'], ['vencida', 'Vencida']] },
        'licitacion.partida': { participacion: [['sin_decidir', 'Sin decidir'], ['participamos', 'Participamos'], ['descartada', 'Descartada']] },
        'licitacion.expediente': { state: [['borrador', 'Borrador'], ['en_armado', 'En armado'], ['listo', 'Listo para publicar'], ['publicado', 'Publicado']] },
        'licitacion.documento': { tipo: [['prov_ficha', 'Ficha técnica'], ['propio_pago_bases', 'Pago de bases']], state: [['pendiente', 'Pendiente'], ['en_gestion', 'En gestión'], ['recibido', 'Recibido'], ['vencido', 'Vencido'], ['no_aplica', 'No aplica']], origen: [['proveedor', 'Proveedor'], ['propio', 'Empresa licitante']] },
        'licitacion.pregunta': { state: [['borrador', 'Borrador'], ['revision_legal', 'En revisión legal'], ['lista', 'Lista para enviar'], ['enviada', 'Enviada'], ['respondida', 'Respondida']] },
        'licitacion.carta.apoyo': { state: [['borrador', 'Borrador'], ['enviada', 'Enviada'], ['respondida', 'Respondida']] },
        'licitacion.incidencia': { origen: [['procedimiento', 'Procedimiento'], ['partida', 'Partida'], ['carga', 'Fila pendiente de catálogo']], severidad: [['bloqueante', 'Bloqueante'], ['advertencia', 'Advertencia']], state: [['abierta', 'Abierta'], ['resuelta', 'Resuelta'], ['ignorada', 'Ignorada']] },
        'licitacion.carga': { state: [['borrador', 'Borrador'], ['previsualizada', 'Previsualizada'], ['confirmada', 'Confirmada'], ['rechazada', 'Rechazada'], ['pendiente_asignacion', 'Pendiente de asignación']], tipo_detectado: [['listado', 'Listado de procedimientos'], ['detalle', 'Detalle de partidas'], ['catalogo', 'Catálogo SAI'], ['anexo', 'Anexo']], subtipo_detectado: [['listado', 'Listado']], origen_portal: [['comprasmx', 'ComprasMX']] },
        'licitacion.fecha.fatal': { tipo: [['junta', 'Junta de aclaraciones'], ['preguntas', 'Límite de preguntas'], ['muestras', 'Entrega de muestras'], ['apertura', 'Apertura'], ['fallo', 'Fallo']] },
    };
    const tables = {
        'licitacion.procedimiento': procs, 'licitacion.partida': partidas, 'licitacion.expediente': expedientes, 'licitacion.incidencia': incidencias,
        'licitacion.carga': cargas, 'licitacion.fecha.fatal': fechas, 'licitacion.pregunta': preguntas, 'licitacion.costeo.linea': costeo,
        'licitacion.documento': documentos, 'licitacion.carta.apoyo': cartas, 'licitacion.entidad.federativa': [{ id: 32, nombre: 'Zacatecas', display_name: 'Zacatecas' }],
        'licitacion.partida.proveedor': [{ id: 91, partida_id: [11, '25301001'], partner_id: [7, 'Proveedor Uno'] }], 'licitacion.aparicion': [{ id: 1 }, { id: 2 }],
    };
    const calls = [];
    const actions = [];
    w.services = {
        orm: {
            call: async (model, method, args, kwargs) => {
                calls.push({ model, method, args, kwargs });
                if (method === 'fields_get') return Object.fromEntries(args[0].map((name) => [name, { selection: (selections[model] || {})[name] || [], string: name }]));
                if (method === 'formatted_read_group') return [{ state: 'detectado', __count: 1 }, { state: 'analisis', __count: 1 }, { state: 'propuesta', __count: 1 }, { state: 'descartado', __count: 1 }];
                if (method === 'onchange') return { value: { tipo_detectado: 'Listado de procedimientos', detalle_borrador: false } };
                if (method.startsWith('action_')) return { type: 'ir.actions.act_window', res_model: model, target: 'new' };
                throw new Error('RPC no simulado: ' + model + '.' + method);
            },
            searchRead: async (model, domain, fields, kwargs) => {
                calls.push({ model, method: 'search_read', domain });
                // el archivo de prueba no coincide con ninguna carga confirmada (huella distinta)
                if ((domain || []).some((leaf) => Array.isArray(leaf) && leaf[0] === 'binary_sha256')) return [];
                return (tables[model] || []).map((r) => ({ ...r }));
            },
            read: async (model, ids, fields) => { calls.push({ model, method: 'read', ids }); return (tables[model] || []).filter((r) => ids.includes(r.id)).map((r) => ({ ...r })); },
            searchCount: async (model) => (tables[model] || []).length,
            formattedReadGroup: async (model) => (model === 'licitacion.expediente' ? [{ state: 'en_armado', __count: 1 }, { state: 'listo', __count: 1 }] : [{ state: 'detectado', __count: 1 }, { state: 'analisis', __count: 1 }, { state: 'propuesta', __count: 1 }, { state: 'descartado', __count: 1 }]),
            create: async (model, values) => { calls.push({ model, method: 'create', values }); return [99]; },
        },
        action: { doAction: async (action, options) => { actions.push({ action, options }); if (options && options.onClose) await options.onClose(); } },
        dialog: { add: (component, props) => { w.dialogs.push({ component, props }); } },
        notification: { add: (message, options) => { w.notifications.push({ message, options }); } },
    };
    w.dialogs = []; w.notifications = [];

    const sources = ['meta.js', 'data.js', 'nav.js', 'components.js', 'header.js', 'inicio.js', 'procedimientos.js', 'procedimiento.js', 'expedientes.js', 'expediente.js', 'carga.js', 'hub.js']
        .map((f) => strip(read(path.join(SRC, 'js/lp', f))));
    w.eval(`const { Component, useState, useRef, onWillStart, onWillUpdateProps, onMounted, markup } = owl;
        const DateTime = luxon.DateTime;
        const _t = (text, ...args) => { let i = 0; return String(text).replace(/%s/g, () => args[i++]); };
        const registry = { category: () => ({ add() {} }) };
        const useService = (name) => window.services[name];
        const useDebounced = (fn) => Object.assign(() => fn(), { cancel() {} });
        const user = { name: 'Ana Prueba', userId: 2, activeCompany: { id: 1, name: 'BioTecZac' }, activeCompanies: [{ id: 1, name: 'BioTecZac' }], allowedCompanies: [{ id: 1, name: 'BioTecZac' }, { id: 2, name: 'Valma' }] };
        const deserializeDateTime = (s) => DateTime.fromSQL(s, { zone: 'utc' }).toLocal();
        const deserializeDate = (s) => DateTime.fromISO(s);
        const formatDateTime = (d) => d.toFormat('dd/MM/yyyy HH:mm');
        const formatDate = (d) => d.toFormat('dd/MM/yyyy');
        const serializeDateTime = (d) => d.toUTC().toFormat('yyyy-MM-dd HH:mm:ss');
        const serializeDate = (d) => d.toISODate();
        class ConfirmationDialog extends Component { static template = owl.xml\`<div class="lp-test-confirm"/>\`; static props = ['*']; }
        class DateTimeInput extends Component { static template = owl.xml\`<input class="o_datetime_input"/>\`; static props = ['*']; }
        ${sources.join('\n')}
        window.LpHub = LpHub;`);

    const doc = w.document;
    const mount = async (context) => {
        // los objetos se crean en el realm de la ventana: OWL valida props con los constructores de ese realm
        const props = w.eval('(' + JSON.stringify({ action: { context } }) + ')');
        const app = new w.owl.App(w.LpHub, { templates, dev: true, props });
        const root = await app.mount(doc.body);
        await tick(60);
        return { app, root };
    };
    const text = () => doc.body.textContent.replace(/\s+/g, ' ');

    // ------------------------------------------------------------ inicio
    let { app, root } = await mount({ lp_view: 'inicio' });
    assert.match(text(), /Ana/, 'saludo con el nombre del usuario');
    assert.equal(doc.querySelectorAll('.lp-pipeline__stage').length, 6, 'seis etapas en el flujo');
    assert.equal(doc.querySelectorAll('.lp-kpi').length, 5, 'cinco indicadores');
    assert.match(text(), /Requieren tu decisión/);
    assert.ok(doc.querySelector('.lp-agenda__item'), 'agenda con eventos');
    doc.querySelector('.lp-pipeline__stage').click(); await tick();
    assert.equal(actions.at(-1).action.context.lp_view, 'procedimientos', 'la etapa navega a la lista');
    doc.querySelector('.lp-row .lp-btn').click(); await tick();
    assert.ok(calls.some((c) => c.method === 'action_cribar'), 'Cribar llama al método existente');
    app.destroy();

    // ------------------------------------------------------------ procedimientos
    ({ app } = await mount({ lp_view: 'procedimientos', lp_filters: { state: 'detectado' } }));
    assert.equal(doc.querySelectorAll('.lp-proc').length, 4, 'tarjetas de procedimiento');
    assert.ok(doc.querySelector('.lp-chip--active'), 'chip de etapa activo');
    doc.querySelector('.lp-proc__main').click(); await tick();
    assert.equal(actions.at(-1).action.context.lp_view, 'procedimiento', 'la tarjeta abre el flujo guiado');
    const search = doc.querySelector('.lp-search input');
    search.value = 'curación'; search.dispatchEvent(new w.Event('input', { bubbles: true })); await tick(40);
    assert.ok(calls.some((c) => c.method === 'search_read' && c.model === 'licitacion.procedimiento'), 'la búsqueda consulta al servidor');
    app.destroy();

    // ------------------------------------------------------------ procedimiento guiado (detectado, analisis, descartado)
    ({ app } = await mount({ lp_view: 'procedimiento', lp_id: 1 }));
    assert.equal(doc.querySelectorAll('.lp-stepper__step').length, 6);
    assert.ok(doc.querySelector('.lp-stepper__step--current'), 'etapa actual resaltada');
    assert.match(text(), /Ahora toca/);
    assert.match(text(), /Fechas fatales/);
    assert.ok(doc.querySelector('.lp-timeline__item'), 'línea de tiempo con las cinco fechas');
    assert.match(text(), /Incidencias abiertas/);
    doc.querySelectorAll('.lp-subtabs__tab')[1].click(); await tick();
    assert.equal(doc.querySelectorAll('.lp-table--partidas tbody tr').length, 3, 'tres renglones');
    assert.match(text(), /Confirma «Participamos»/, 'renglones bloqueados en detectado');
    doc.querySelectorAll('.lp-subtabs__tab')[2].click(); await tick();
    assert.match(text(), /Todavía no hay expedientes|Sin expedientes|expedientes/i);
    // Participamos abre la confirmación y, al aceptar, llama al método
    doc.querySelector('.lp-now__actions .lp-btn--primary').click(); await tick();
    assert.equal(w.dialogs.at(-1).component.name, 'ConfirmationDialog');
    await w.dialogs.at(-1).props.confirm(); await tick(40);
    assert.ok(calls.some((c) => c.method === 'action_pasar_a_analisis'), 'Participamos llama a action_pasar_a_analisis');
    app.destroy();
    // active_model/active_id desde el botón Vista guiada del formulario nativo
    ({ app } = await mount({ active_model: 'licitacion.procedimiento', active_id: 2 }));
    assert.match(text(), /En análisis/);
    doc.querySelectorAll('.lp-subtabs__tab')[1].click(); await tick();
    const checks = doc.querySelectorAll('.lp-table--partidas tbody input[type=checkbox]');
    assert.ok(checks.length >= 2, 'selección múltiple disponible en análisis');
    checks[0].click(); checks[1].click(); await tick();
    doc.querySelector('.lp-toolbar__group .lp-btn--outline').click(); await tick();
    assert.ok(calls.some((c) => c.method === 'action_propagar_empresas' && c.args[0].length === 2), 'propagar usa los renglones seleccionados');
    doc.querySelectorAll('.lp-table--partidas tbody .lp-btn')[0].click(); await tick();
    assert.equal(actions.at(-1).action.res_model, 'licitacion.partida', 'Asignar abre el formulario nativo del renglón');
    assert.equal(actions.at(-1).action.target, 'new');
    app.destroy();
    ({ app } = await mount({ lp_view: 'procedimiento', lp_id: 4 }));
    assert.match(text(), /Descartado/);
    assert.match(text(), /Fuera de alcance/, 'nota de criba visible');
    assert.ok(doc.querySelector('.lp-banner'), 'banner de cierre por criba');
    app.destroy();

    // ------------------------------------------------------------ expedientes y expediente guiado
    ({ app } = await mount({ lp_view: 'expedientes' }));
    assert.equal(doc.querySelectorAll('.lp-exp').length, 2);
    assert.match(text(), /Pago de bases/, 'bloqueantes visibles en la tarjeta');
    app.destroy();
    ({ app } = await mount({ lp_view: 'expediente', lp_id: 21 }));
    assert.equal(doc.querySelectorAll('.lp-stepper__step').length, 4);
    assert.match(text(), /Costeo: 1 de 2 renglones/);
    assert.match(text(), /Pago de bases/);
    assert.ok(doc.querySelector('.lp-btn--primary[disabled]'), 'Marcar listo bloqueado con bloqueantes');
    const tabs = [...doc.querySelectorAll('.lp-subtabs__tab')];
    tabs[0].click(); await tick(); assert.ok(doc.querySelector('.lp-qa__item'), 'pregunta listada');
    tabs[1].click(); await tick(); assert.equal(doc.querySelectorAll('.lp-table--costeo tbody tr').length, 2); assert.match(text(), /Cantidad pendiente/);
    tabs[2].click(); await tick(); assert.equal(doc.querySelectorAll('.lp-doc').length, 2);
    tabs[3].click(); await tick(); assert.ok(doc.querySelector('.lp-row__actions .lp-btn--primary'), 'Enviar carta disponible en borrador');
    doc.querySelector('.lp-row__actions .lp-btn--primary').click(); await tick();
    await w.dialogs.at(-1).props.confirm(); await tick(40);
    assert.ok(calls.some((c) => c.model === 'licitacion.carta.apoyo' && c.method === 'action_enviar'));
    doc.querySelector('.lp-page__actions .lp-btn--outline').click(); await tick();
    assert.equal(actions.at(-1).action, 'licitaciones_publicas.report_expediente', 'PDF abre la acción de reporte');
    assert.deepEqual([...actions.at(-1).options.additionalContext.active_ids], [21]);
    app.destroy();

    // ------------------------------------------------------------ carga guiada
    ({ app, root } = await mount({ lp_view: 'carga' }));
    assert.ok(doc.querySelector('.lp-dropzone'), 'zona de arrastre');
    assert.equal(doc.querySelectorAll('.lp-stepper__step').length, 3);
    // simular archivo leído con el método público del componente de carga (mismo camino que la zona de arrastre)
    const file = w.eval(`({ name: 'listado.xlsx', size: 2048, base64: 'UEsDBBQ=', sha256: '${'a'.repeat(64)}' })`);
    const dropzoneComponent = (() => { const nodes = []; const walk = (n) => { if (!n) return; if (n.component) nodes.push(n.component); for (const c of Object.values(n.children || {})) walk(c); }; walk(root.__owl__); return nodes.find((c) => c.constructor.name === 'LpCarga'); })();
    assert.ok(dropzoneComponent, 'componente de carga localizado');
    await dropzoneComponent.onFile(file); await tick(40);
    assert.match(text(), /Formato reconocido: Listado de procedimientos/, 'detección con el onchange del asistente');
    doc.querySelector('.lp-wizard__foot .lp-btn--primary').click(); await tick();
    assert.match(text(), /Datos de la descarga/);
    doc.querySelector('.lp-wizard__foot .lp-btn--primary').click(); await tick();
    assert.match(text(), /Revisar y previsualizar/);
    doc.querySelector('.lp-wizard__actions .lp-btn--primary').click(); await tick(60);
    const created = calls.find((c) => c.method === 'create' && c.model === 'licitacion.carga.wizard');
    assert.ok(created, 'se crea el asistente nativo con los datos capturados');
    assert.equal(created.values[0].archivo_nombre, 'listado.xlsx');
    assert.ok(calls.some((c) => c.method === 'action_preview'), 'y se pide la previsualización');
    assert.match(text(), /Carga procesada/, 'pantalla final tras cerrar la previsualización');
    app.destroy();

    const errors = w.notifications.filter((n) => n.options && n.options.type === 'danger');
    assert.deepEqual(errors, [], 'sin notificaciones de error: ' + JSON.stringify(errors));
    console.log('Centro de Licitaciones: humo OK — inicio, procedimientos, procedimiento (detectado/análisis/descartado), expedientes, expediente y carga renderizan y ejecutan sus acciones.');
})().catch((error) => { console.error(error); process.exit(1); });
