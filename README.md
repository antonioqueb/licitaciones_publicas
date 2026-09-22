# Gestión de Licitaciones Públicas · Odoo 19

Implementación inicial del brief v1: cargas Excel con previsualización, criba,
asignación de empresas y proveedores, expedientes por empresa, agenda,
incidencias y exportables. Nombre técnico: `licitaciones_publicas`.

**Estado de entrega: desarrollo pendiente de validación en Odoo. No es una v1
aceptada para producción.** Se ejecutaron 46 pruebas independientes del servidor,
la compilación Python, la comprobación de sintaxis JavaScript y la revisión
estructural de 18 XML. Los ensayos de instalación Enterprise encontraron un
dominio inválido y un destino de acción obsoleto, ambos corregidos. Queda pendiente
repetir la instalación y ejecutar las pruebas ORM/PDF, cobertura global ≥80%, CI remoto, demo con Excel
del cliente y capturas reales. Véase [evidencia](docs/verificacion.md).

## Instalación en desarrollo

1. Disponer de Odoo **19.0** y PostgreSQL, con acceso al código Enterprise si se
   utiliza esa edición. Odoo Online sin código personalizado no es un destino
   de instalación de este addon.
2. Clonar este repositorio en un directorio denominado `licitaciones_publicas`
   dentro de `addons_path`.
3. Añadir [OCA reporting-engine 19.0](https://github.com/OCA/reporting-engine/tree/19.0)
   a `addons_path`; se requiere el addon `report_xlsx`.
4. Instalar `openpyxl` y `xlsxwriter` en el Python del servidor. Instalar
   `wkhtmltopdf` compatible con ese servidor para los tres reportes PDF.
5. Configurar `data_dir` en una ubicación persistente del servidor. El parámetro
   nativo `ir_attachment.location` debe ser `file` para almacenar los binarios
   en `<data_dir>/filestore/<base>`. Se conservan metadatos en PostgreSQL.
   La copia de seguridad debe incluir base y filestore. Este módulo no mueve
   automáticamente los adjuntos ya existentes.
6. Instalar en una base de desarrollo, por ejemplo:

   ```sh
   odoo -c /etc/odoo/odoo.conf -d BASE_DEV \
     -i licitaciones_publicas --load-language=es_MX --stop-after-init
   ```

7. Asignar **Usuario de Licitaciones** o **Administrador de Licitaciones** a los
   usuarios. Activar las empresas autorizadas en el selector nativo de Odoo.
   Configurar las empresas existentes con moneda MXN y los usuarios con idioma
   Español (México) y zona horaria adecuada.
8. Marcar los contactos existentes como proveedores de licitaciones, con
   contacto compartido (`company_id` vacío), correo y agrupadores CUCoP+.
   La demo no crea BioTecZac, Valma, Pro Omnimedic ni proveedores duplicados.
9. Revisar correo saliente, responsable por procedimiento y los cuatro cron.
   El módulo se entrega sin realizar envíos ni despliegues sobre una instancia.

No depende de `documents` porque usa `ir.attachment` según A-03. La firma
escaneada del representante es opcional por empresa y aparece condicionalmente
en los PDF. No equivale a una firma electrónica.

## Dependencias en Docker Compose

`requirements.txt` reúne `openpyxl`, `xlsxwriter` y `xlrd` (esta última también es
dependencia declarada de `report_xlsx`). Las pruebas incluyen ese mismo archivo
desde `requirements-test.txt`.

El `Dockerfile` añade esas librerías y el addon **report_xlsx** a una imagen Odoo
19. El addon se obtiene del [wheel publicado por OCA en PyPI](https://pypi.org/project/odoo-addon-report-xlsx/19.0.1.0.2.2/),
fijado por versión y SHA-256 en `requirements-odoo.txt`. Se extrae con `--no-deps`
para conservar la distribución Odoo instalada en la imagen y se copia al
directorio nativo de addons. Los montajes de `/mnt/extra-addons` de cada instancia
no ocultan esa dependencia. El build verifica la versión de Odoo y los imports.

La imagen base predeterminada queda fijada al mismo digest de Odoo que el usuario
confirmó en los contenedores actuales de QA y producción:
`sha256:f99ffac95cb39a0924622ea4118481c95651d9c84187e5b30a21c2cc4419c7dd`.
Así, la construcción no introduce una actualización implícita de Odoo.

Construcción independiente desde la raíz de este repositorio:

```sh
docker compose -f compose.dependencies.yaml build odoo
```

Para el servidor Bioteczac, ejecutar allí **después de copiar/publicar estos
archivos nuevos**, desde el clon del módulo:

```sh
cd /opt/bioteczac/qa/addons/licitaciones_publicas
bash scripts/build_dependencies.sh both
```

También admite `qa` o `production`. El script lee `services.odoo.image` del
`/opt/bioteczac/<instancia>/compose.json` existente y lo pasa como
`ODOO_BASE_IMAGE`; conserva así la versión/digest de Odoo de cada instancia.
Construye con `docker compose build odoo` las imágenes
`bioteczac-odoo-qa-licitaciones:19.0.1.0.0` y
`bioteczac-odoo-production-licitaciones:19.0.1.0.0`.

La construcción deja listas las imágenes; no cambia el servicio activo ni instala
módulos en la base. Para usarlas en el despliegue, la configuración persistente del
servicio `odoo` de cada entorno debe apuntar a su nueva imagen. El runtime local
`manager.py` genera `compose.json` y el actualizador lo utiliza con `-f` explícito:
un archivo override aislado no se aplica automáticamente. Hay que conservar esa
selección también al regenerar la configuración del runtime. Revisar la versión
real del runtime remoto antes de cambiarla. La instalación de `licitaciones_publicas`
y su dependencia `report_xlsx` se realiza después, primero en QA.

Antes de actualizar producción, comprobar los montajes reales de PostgreSQL y del
filestore, generar un respaldo consistente de base y archivos junto con la
configuración, conservar una copia cifrada fuera del servidor y probar su
restauración en un entorno aislado. Un checksum o `pg_restore --list` no sustituyen
esa prueba de recuperación. No usar `sync`/`qa-refresh` para instalar dependencias,
ni eliminar volúmenes o directorios de datos. La actualización debe conservar los
montajes existentes. El comando documentado `bioteczac backup` pausa temporalmente
Odoo/Nginx de producción para obtener un corte consistente y los vuelve a iniciar;
hay que verificar su versión instalada y prever esa interrupción antes de ejecutarlo.

Validación local de estos archivos: configuración Compose y sintaxis comprobables
sin daemon. **El build no se ha completado en este entorno**: SSH está bloqueado y
el socket local de Docker devuelve `permission denied`.

## Operación

- **Agenda:** cinco tipos de fecha en una vista SQL, calendario y lista, filtros
  próximas 72 horas, vencidas sin actuar, juntas y preguntas.
- **Cargas → Nueva carga:** archivo `.xlsx`, fecha declarada, origen, zona
  horaria y alcance de búsqueda. Se utiliza la primera hoja y se buscan los
  encabezados entre las filas 1 y 5. El detalle sin padre conocido permanece
  pendiente hasta asignarlo con justificación.
- **Preview:** nuevos, cambios, sin cambios y ya no aparecen. Los catálogos y
  registros destino se escriben únicamente al confirmar. Un archivo vacío o
  una previsualización obsoleta no puede confirmarse. La carga rechazada y su
  original se conservan.
- **Procedimientos:** lista, kanban por estado interno, criba individual y en
  lote, responsable, semáforo de juntas, fechas y trazabilidad en chatter.
- **Renglones:** confirmar En análisis, abrir un renglón y agregar empresas en
  la lista nativa. La primera es Principal; las demás son Secundarias. Retirar
  la principal promueve la siguiente. El asa de orden permite reordenar. Los
  chips reflejan las asignaciones. Los proveedores tienen autocompletado nativo
  y sugerencias por agrupador CUCoP+. En la lista independiente de Renglones,
  las acciones por selección permiten propagar empresas o proveedores.
- **Generar expedientes:** resumen por empresa antes de confirmar. Se reutilizan
  los expedientes y cartas existentes. No envía correos automáticamente.
- **Expedientes:** preguntas, costeo, documentos de proveedores, documentos
  propios y resumen. Archivos sustituidos generan versiones conservadas.
  Publicar propuesta cambia el estado interno del expediente: no publica
  en ComprasMX. Se bloquea si quedan documentos obligatorios incompletos o
  vencidos, o incidencias bloqueantes abiertas.
- **Incidencias:** comparación de valores, resolver/ignorar con nota. Resolver
  aplica solo campos permitidos y comprueba que el valor anterior siga vigente.
  Cambiar la entidad de una unidad compradora requiere permisos de catálogo.
- **Reportes:** menú Imprimir para carta, expediente y preguntas listas en PDF;
  costeo, partidas y checklist en XLSX. Cartas de expedientes también en ZIP.
  «Enviar al proveedor» coloca el correo en la cola; «Enviada» describe esa
  entrega a la cola, no confirma recepción del destinatario.

## Reglas que conviene conocer

**Dos estados:** el importador administra el estatus del portal y conserva el
estado interno. El cambio interno se realiza mediante acciones, con validación
en servidor. Descartar o declarar no viable requiere motivo aplicable.

**Reapertura provisional:** un descartado necesita una nueva carga con al menos
una fecha límite no vacía que haya cambiado. Se registra aviso y actividad;
después el usuario decide mediante criba. No viable puede reabrirse manualmente.
Esta interpretación de la contradicción de 16.3.10 fue consultada y sigue sin
confirmación. [Decisiones y discrepancias](docs/decisiones.md).

**Ausencias:** se compara con la última carga confirmada del mismo origen,
alcance, tipo, procedimiento y conjunto de empresas activas. «Alcance» debe
representar exactamente los filtros aplicados en el portal. Un snapshot anterior
no debe sustituir otro posterior. Nunca se borran partidas por desaparecer.

**Cantidades:** `cantidad` conserva la solicitada, incluido cero; si no se
proporciona se utiliza la máxima. Mínima y máxima se conservan. La terna de
identidad incluye la descripción exacta, no solamente la clave CUCoP+.

**Costeo:** margen = `(precio − costo) / precio × 100`; precio cero produce
margen cero. Una secundaria requiere costeo previo de la principal. Su recargo
sugerido es el margen principal más un valor aleatorio entre 5 y 15 puntos;
la validación exige siempre un valor mayor al margen principal. Cambiar un
precio principal vuelve a validar las secundarias. Se requiere tener activas
todas las empresas asignadas para editar esos costes; no se eluden las reglas
de acceso para leer el margen de otra empresa. El recargo no cambia por sí mismo
el precio unitario. Asignaciones con costeo o cartas enviadas tienen restricciones
de retirada para conservar el expediente.

**Retención:** procedimientos, partidas, cargas, snapshots, expedientes,
preguntas, costes, documentos y cartas no se borran. Procedimientos, expedientes
y preguntas admiten archivo cuando corresponde. Catálogos se archivan. Solo
las asignaciones y asistentes temporales permiten eliminación, con las
validaciones descritas. La ubicación futura de archivos se puede documentar
en Ajustes; no activa un almacenamiento NFS/S3/SharePoint.

**Avisos:** cron horario para juntas a ≤72 h y a ≤24 h si continúa pendiente
el primer aviso; otro para incidencias bloqueantes (24 h por defecto,
configurable) y otro para documentos vencidos. El semáforo almacenado del kanban
se actualiza por cambios de fecha y cada hora. Se generan actividades y chatter.
La recepción por correo depende de la configuración de notificaciones de Odoo.

## Pruebas

Pruebas sin Odoo:

```sh
python3 -m pip install -r requirements-test.txt
python3 scripts/check_static.py
python3 -m unittest discover -s tests/standalone -v
node --check static/src/js/partida_empresas.js
```

Pruebas de integración en una base desechable:

```sh
odoo -c /etc/odoo/odoo.conf -d LICITACIONES_TEST \
  -i licitaciones_publicas --test-enable --test-tags=/licitaciones_publicas \
  --load-language=es_MX --without-demo=all --stop-after-init --max-cron-threads=0
```

[CI](.github/workflows/ci.yml) prepara Odoo 19, PostgreSQL y `report_xlsx`,
ejecuta pruebas de integración/PDF/XLSX y exige cobertura global de código
propio ≥80%. **El workflow está escrito pero aún no se ha ejecutado**; no existe
un resultado verde ni una medición global certificada. El job público usa
el runtime base de Odoo; la aceptación debe repetirse en Enterprise.

Los tests generan 117 y 50 filas **sintéticas**. La prueba con los tres archivos
del cliente se omite explícitamente si no se suministran en
[tests/fixtures](tests/fixtures/README.md). Esa omisión no satisface la aceptación.
La calibración y prueba integral del listado oficial también permanecen pendientes.

## Pendiente antes de aceptar v1

1. Recibir los 8 HTML y los dos documentos referenciados; validar la UX y
   adaptar las vistas. Los chips actuales son de presentación, con edición
   nativa en el renglón. El stepper es informativo; no se han implementado
   los paneles laterales personalizados de agenda ni la dropzone propia.
2. Recibir los tres Excel y el listado oficial. Calibrar los encabezados de
   listado, comprobar 117/50/1/26 filas reales y cargar la demo en desarrollo.
3. Confirmar la regla contradictoria de reapertura; definir ubicación final,
   retención y uso de la firma escaneada.
4. Instalar en Odoo 19 Enterprise, corregir los fallos que detecte el runtime,
   ejecutar todas las pruebas y alcanzar cobertura global ≥80% medida.
5. Revisar PDF renderizados, XLSX, correo, traducciones cargadas y tablet
   1024×768. Obtener capturas reales de las ocho vistas. No se incluyen
   screenshots inventados ni renders HTML presentados como Odoo.
6. Publicar el repositorio en el remoto acordado y ejecutar CI. El repositorio
   entregado por esta sesión es local.

## Fuera de alcance v1

Órdenes de compra/venta y contabilidad post-fallo; firma electrónica; portal
público para proveedores; app móvil/PWA; scraping o API ComprasMX; idiomas
adicionales; CFDI y complementos de pago; dashboards ejecutivos y analítica
histórica de decisiones. No se implementa el roadmap v1.1–v3.0.

Licencia declarada: OPL-1. `report_xlsx` conserva su licencia independiente.
