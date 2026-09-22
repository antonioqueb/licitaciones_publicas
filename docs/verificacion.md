# Verificación local · 21/09/2026

## Ejecutado

| Comprobación | Resultado |
|---|---|
| `unittest discover -s tests/standalone -v` | 39 pruebas correctas |
| `scripts/check_static.py` | Manifest, campos de vistas, botones y ACL coherentes |
| `compileall` | Sin errores de sintaxis Python |
| `node --check static/src/js/partida_empresas.js` | Sin errores de sintaxis |
| Parseo con `lxml.etree` | 18 XML bien formados |
| `msgfmt --check` | Catálogo es_MX válido sintácticamente |

El runtime local utilizado para Excel fue el Python 3.12 del entorno Codex,
con `openpyxl` y `xlsxwriter` disponibles. Los tests abren los XLSX resultantes
con `openpyxl` y comprueban contenido, formato monetario, fechas, congelación
de cabecera, filtros y protección contra fórmulas en texto importado.

Estas pruebas no simulan el ORM ni certifican que una vista se instale. No se
reporta un porcentaje global de cobertura porque no se ha medido.

## Impedimentos observados

- No aparecieron `Especificacion_Diseno_Modulo.md`, los 8 dummies ni los Excel
  citados en las rutas locales revisadas. Se solicitó la ubicación al usuario.
- Docker devolvió denegación de acceso al socket local.
- `pg_isready` no encontró servicio PostgreSQL local.
- No hay paquete o fuente Odoo instalado en el Python disponible.
- La descarga del código por shell falló por resolución DNS en el sandbox.
- El Python de sistema también está bloqueado por la aceptación pendiente de
  la licencia de Xcode; se utilizó el runtime alternativo para las pruebas puras.

## Pendiente de ejecución

Instalación y actualización en Enterprise; tests ORM y de seguridad real;
PDF con wkhtmltopdf; cobertura de todo el addon ≥80%; CI remoto; muestras
oficiales; correo/cron en desarrollo; revisión visual y screenshots.

El workflow y las pruebas se entregan como código revisable, sin atribuirles
un resultado de ejecución que aún no existe. El README registra además las
diferencias funcionales de UI pendientes frente al brief.

## Primer ensayo remoto y corrección · 22/09/2026 UTC

La instalación en una base desechable de Odoo 19 Enterprise se detuvo al validar
la vista del asistente de criba. El dominio Python de `motivo_id` tenía una comilla
sin cerrar dentro de una cadena válida de Python; la compilación del archivo no
detectaba esa sintaxis interna. No llegaron a ejecutarse las pruebas ORM/PDF.

Se sustituyó ese dominio por una lista literal y se amplió `check_static.py` para
validar sintaxis de dominios/contextos en cadenas Python y de expresiones XML,
sin evaluarlas. Se agregaron cuatro pruebas que reproducen el defecto y comprueban
expresiones dinámicas y modificadores de vistas. Resultado local: **43 pruebas
independientes correctas** y comprobación estática de 33 Python y 18 XML aprobada.
La repetición del ensayo completo en Odoo sigue pendiente.

La imagen con dependencias también se construyó y verificó en el servidor después
de sustituir `odoo.__file__` por búsqueda en `odoo.addons.__path__`, compatible con
el paquete namespace de Odoo 19. Esta corrección del Dockerfile queda incluida en
el repositorio. La ejecución fallida de la instalación se detuvo antes de actualizar
las bases de negocio de QA y producción.

## Segundo ensayo remoto y corrección · 22/09/2026 UTC

Con el commit `69d931d` publicado, la instalación avanzó hasta
`views/settings_views.xml:4`. Odoo rechazó `ir.actions.act_window.target = inline`.
Se reemplazó por `current` tanto en el XML como en su generador. El checker ahora
comprueba los destinos de acciones de ventana y tiene tres pruebas adicionales:
rechazo de `inline`, aceptación de los destinos vigentes y separación de acciones
URL/campos de vistas. La selección se contrastó con el
[modelo oficial de acciones de Odoo 19](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/ir_actions.py).
También se asignaron roles accesibles a los tres avisos que advertía el log.

Durante la revisión de las pruebas se corrigió la llamada de PDF para pasar
`force_report_rendering=True`. El
[motor de reportes de Odoo 19](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/ir_actions_report.py)
devuelve HTML durante los tests si no se fuerza el PDF. Se conservan las
comprobaciones de formato PDF, cabecera `%PDF-` y tamaño mayor a 5 KB para los tres
reportes; este ajuste aún debe ejecutarse en el servidor.

Resultado local: **46 pruebas independientes correctas**, checker de 33 Python y
18 XML aprobado y `git diff --check` sin errores. La evidencia remota del fallo
está en `evidence/licitaciones-instalar-qa.I49yXUh5/review/odoo-tests.log` del
workspace de despliegue. El ensayo se detuvo en la base desechable
`licitaciones_test`, antes de las pruebas ORM/PDF y antes de actualizar QA. No se
ejecutó una actualización de producción. Instalación y pruebas completas siguen
pendientes de una nueva ejecución con esta revisión publicada.

## Tercer ensayo: captura de asistentes y solicitudes PDF · 22/09/2026 UTC

El release `licitaciones-20260922T052525384904Z`, con `491f5fa`, superó la carga de
vistas y llegó a las pruebas ORM. `test_unknown_identifier_requires_assignment`
encontró que `modal()` creaba el asistente de asignación antes de que el usuario
indicara el procedimiento y la justificación obligatorios. Se abría con datos
incompletos y PostgreSQL rechazaba `procedimiento_id = NULL`.

Los asistentes de captura ahora se abren sin registro persistido, con valores
`default_*` en el contexto de la acción. Se mantienen las restricciones de campos
obligatorios al guardar. Esto corrige también los asistentes de resolución y
propagación, que seguían el mismo patrón. Solo el preview se crea anticipadamente,
pues dispone de todos sus datos y materializa las filas del diff antes de mostrarse.
El contexto interno de importación no se devuelve al cliente.

Las pruebas ORM utilizan `Form` para recorrer apertura, captura, validación de
campos requeridos y confirmación: asignación pendiente, criba por lote, generación
de expedientes, resolución/ignoración y propagación de empresas/proveedores. Se
añadió una comprobación de serialización de la acción sin tokens internos.

El ensayo se quedó en el primer PDF tras un timeout HTTP. La prueba heredaba solo
de `TransactionCase`; ahora combina los fixtures con `HttpCase`, que prepara el
cursor compartido y permite las solicitudes HTTP de wkhtmltopdf. Este mecanismo
está implementado en el [framework oficial de pruebas de Odoo 19](https://github.com/odoo/odoo/blob/19.0/odoo/tests/common.py).
Se conserva `force_report_rendering=True` y la validación de los tres PDF reales;
no se reemplaza la salida por HTML ni por archivos simulados.

Validación local de la revisión: **46 tests independientes correctos**, checker
de 33 Python/18 XML y `git diff --check` aprobados. Las pruebas ORM nuevas y PDF
corregidas todavía requieren repetición en el servidor. El fragmento remoto
disponible confirma el error del asistente; no permite dar por aprobada la suite.
La actualización de QA permanece detrás de esta prueba aislada y el instalador
no ejecuta una actualización de producción.
