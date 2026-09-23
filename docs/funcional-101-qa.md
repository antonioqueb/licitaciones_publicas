# Funcional 101 — Cruces de catálogo sin pérdida de filas

Versión `19.0.4.0.0`, exclusivamente rama `qa/dev01-dev02-importacion` y QA.

## Entidades

Los mismos 32 registros y códigos INEGI se conservan. `codigo_in` expone el código
existente; `estado_base_id` enlaza por XML ID la entidad mexicana de Odoo;
`nombre` consulta su nombre oficial, de solo lectura. No se escribe en
`res.country.state`. `activa`, `notas` y `procedimiento_count` completan la vista.
El administrador solo puede modificar `nombres_alternativos`: CSV de nombres
completos, normalizados con Unidecode, mayúsculas y espacios compactados.

Se busca nombre oficial, nombre histórico de Licitaciones y alias completos.
No se acepta una coincidencia ambigua entre entidades. Veracruz incluye
`VERACRUZ, VERACRUZ DE LA LLAVE`; la migración agrega estos alias conservando los
que ya existan. El nombre visible puede ser «Veracruz» si ese es el nombre del
catálogo base: no se sustituye por un nombre supuesto del ejemplo funcional.

## Importación

`resolve_catalog_value` aplica el mismo mecanismo a entidad, estatus,
contratación, prefijo, carácter y UC. Los catálogos conservan los nombres técnicos
existentes `code`/`name`, equivalentes a código/descripción de la especificación.
La UC se busca por su código; si el listado de 13 columnas no lo publica como
columna aparte, se obtiene del identificador. El nombre de UC publicado se
conserva como contexto, sin renombrar el catálogo automáticamente.

El parser conserva el texto de contratación y ya no limita sus valores a una
lista Python. Un valor desconocido conserva la fila, genera una advertencia
con fila real, archivo, identificador y valor original, y asigna actividad al
administrador. Solo el estatus se crea automáticamente en «Por revisar».
Las FK de UC y contratación pueden quedar vacías; si ya existe un valor válido,
se conserva hasta que el administrador resuelva. Los valores recibidos quedan
en `catalogos_portal`, el snapshot de aparición y el Excel adjunto.

La entidad del procedimiento tiene una FK propia (`entidad_portal_id`) para
corregir un procedimiento sin cambiar retrospectivamente otros procedimientos
de la misma UC. Si no hay asignación propia, se usa la entidad de la UC.

La previsualización no escribe procedimientos ni incidencias. La confirmación
aplica todas las filas y sus advertencias en una sola transacción. Se mantienen
los controles de archivo duplicado DEV-03 y de previsualización obsoleta. Los
errores estructurales de Excel, permisos, identificadores mal formados y fechas
inválidas siguen rechazándose. Las validaciones SAI de detalle conservan su
tratamiento DEV-02: no forman parte de los seis cruces de este cambio.

## Corrección

Resolver/ignorar incidencias de catálogo requiere administrador y nota.
Resolver presenta un selector del catálogo correcto; verifica acceso, actividad
del registro y que la FK no haya cambiado desde la incidencia. Para entidad
ofrece guardar el texto como alias (casilla seleccionada). En otros catálogos
solo muestra una sugerencia de revisar nombres/alias; no los escribe.
Ignorar deja intactas las FK. Ambas acciones registran usuario, fecha y chatter
en el procedimiento. La evidencia original de la incidencia permanece inmutable.

Los incidentes antiguos se conservan con sus estados y severidades anteriores;
no se reescribe el historial de cargas ni se reinterpretan snapshots viejos.

## Dependencias y entrega QA

Se añade `Unidecode==1.4.0` a requirements y al manifest. El script
`ops/actualizar_licitaciones_dev_qa.sh` prepara una imagen derivada de la imagen
actual de dependencias, agregando únicamente esa librería. Primero ejecuta las
pruebas Enterprise aisladas con esa imagen; solo si pasan selecciona la imagen
en los dos archivos propios de QA (`compose.json` y `odoo-image.txt`).

Después, el actualizador habitual respalda QA, actualiza únicamente Licitaciones
y valida conservación de datos, cuentas, adjuntos y disponibilidad. Se acepta
solo el cambio previsto de imagen/contenedor Odoo QA; PostgreSQL, producción,
montajes y runtime compartido deben conservarse. Si falla la actualización del
módulo, su recuperación nativa conserva los datos previos; la dependencia
aditiva puede quedar instalada en la imagen de QA para el siguiente intento.

Se agregan ocho pruebas ORM de aceptación, con ejecución obligatoria antes de
actualizar QA. El resultado real de esas pruebas y el despliegue se registra en
la evidencia generada por el script. No se considera instalado hasta obtener
`LICITACIONES_101_QA_ACTUALIZADO` y comprobar versión/commit en QA.
