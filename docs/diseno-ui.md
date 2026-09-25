# Centro de Licitaciones — diseño de interfaz (19.0.5.0.0)

Rediseño completo de la experiencia del módulo, pedido por el cliente el 25 de septiembre de 2026.
**No cambia ninguna regla de negocio**: modelos, métodos `action_*`, asistentes, permisos, cron y
reportes son los mismos. Cambian la capa de presentación y la navegación.

## Qué se construyó

Una acción de cliente OWL (`licitaciones_publicas.hub`, `static/src/js/lp/hub.js`) con seis espacios
guiados, más un sistema de diseño SCSS propio que también viste las vistas nativas que se reutilizan.

| Espacio (`lp_view`) | Qué muestra | Acciones (todas existentes) |
|---|---|---|
| `inicio` | Saludo, procedimientos por etapa, alertas (juntas en 72 h, vencidas, incidencias bloqueantes, expedientes en armado, cargas sin cerrar), «requieren tu decisión», actividad reciente, agenda de 7 días, incidencias, cargas. Guía «¿Cómo funciona?». | `action_cribar`, navegación |
| `procedimientos` | Tarjetas o filas con etapa, semáforo de junta, apertura, renglones con empresa, incidencias, empresas y responsable. Filtros por etapa, texto, entidad, semáforo, míos, ausentes. | `action_cribar` |
| `procedimiento` | Paso a paso Detectado → Análisis → Preguntas → Costeo → Propuesta → Fallo (o cierre por criba), panel «Ahora toca» con lista de verificación, pestañas Datos del portal / Renglones / Expedientes, lateral con fechas fatales, incidencias y equipo. Renglones con selección múltiple y filtros. | `action_pasar_a_analisis`, `action_cribar`, `action_generar_expedientes`, `action_avanzar`, `action_reabrir` (partida), `action_propagar_empresas/proveedores`, `action_resolver/ignorar` (incidencia); edición del renglón en el formulario nativo en diálogo |
| `expedientes` | Tarjetas por empresa con etapa, conteos, precio, margen y bloqueantes. Filtro por etapa y texto. | navegación |
| `expediente` | Paso a paso Borrador → En armado → Listo → Publicado, «Ahora toca» con bloqueantes, pestañas Preguntas / Costeo / Documentos / Cartas, lateral con procedimiento, resumen y descargas. | `action_armar`, `action_listo`, `action_publicar`, `action_print_cartas_zip`, `action_print_carta`, `action_enviar`, `action_respondida`, reportes PDF/XLSX; capturas en formularios nativos en diálogo |
| `carga` | Tres pasos: archivo (zona de arrastre, huella SHA-256 en el navegador, detección de formato con el `onchange` del asistente, aviso de archivo ya procesado), datos de la descarga (selector de fecha nativo), revisar y previsualizar. | `licitacion.carga.wizard`: `action_preview`, `action_open_existing`, `action_force`; la previsualización y confirmación siguen siendo el asistente nativo |

Los formularios nativos de procedimiento y expediente tienen el botón **Vista guiada** (tipo `action`
hacia `action_lp_procedimiento` / `action_lp_expediente`, con `active_id`). Los menús principales
abren los espacios guiados; **Configuración → Vistas clásicas** conserva las listas nativas, y
**Cargas → Nueva carga (formulario)** el asistente original.

## Sistema de diseño

`static/src/scss/lp/_tokens.scss` define la paleta clínica sobria como variables CSS: teal
`#155e75` (primario), pizarra `#0f172a`–`#f7f9fb` (neutros), verde `#1f6f4f`, ámbar `#9a5b12`,
rojo `#a12a2a` y azul `#2c5f8f` para estados. Cada componente lee `--lp-tone`/`--lp-tone-soft`
y cambia con `lp-tone--ok|warn|danger|info|slate|muted|primary`.

- `_hub.scss`: espacios guiados (encabezado con pestañas, tarjetas, paso a paso, «ahora toca», lista
  de verificación, tablas, línea de tiempo, agenda, zona de arrastre, formularios). Puntos de corte:
  teléfono < 640 px (una columna, tablas como tarjetas con `data-label`), tableta < 1024 px, portátil
  y monitor ≥ 1440 px (contenido centrado a 1480 px, lateral fijo).
- `_native.scss`: las vistas nativas del módulo declaran `class="o_lp_view"` (y `o_lp_wizard` en
  asistentes) desde `scripts/generate_views.py`; con esa clase se ajustan hoja del formulario,
  pestañas, barra de estado, listas, kanban, calendario y diálogos. El resto de Odoo no cambia.

Componentes nativos reutilizados tal cual: calendario de la agenda, `DateTimeInput` (selector de
fecha), autocompletado many2one, chatter, adjuntos, `ConfirmationDialog`, notificaciones y acciones
de reporte.

## Lectura de datos

`static/src/js/lp/data.js` solo usa `search_read`, `read`, `search_count`, `formatted_read_group`
y `fields_get` (etiquetas oficiales de las selecciones), siempre con los permisos y reglas por
empresa del usuario. No hay métodos Python nuevos. Las acciones se ejecutan con `orm.call` a los
métodos existentes y, si devuelven una acción, se abren con el cliente web; al cerrarse se recarga
la pantalla (`nav.js`).

## Verificación

- `python scripts/check_static.py` y `python -m unittest discover -s tests/standalone`: en verde.
- `node --check` de cada archivo JS.
- Compilación de las 14 plantillas OWL con el OWL de Odoo 19 en jsdom y de los tres SCSS con
  dart-sass, sin errores.
- Sin instancia Odoo local: la revisión visual se hace en QA (`https://2.24.78.58:1401/odoo`) antes
  de producción. Las pruebas Odoo del módulo no cambian porque la lógica no cambia.
