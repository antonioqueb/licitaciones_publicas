# DEV-03 · Archivos ya procesados · Solo QA

Versión `19.0.3.0.1`, rama `qa/dev01-dev02-importacion`.
Implementación preparada para el ensayo aislado y actualización de QA.
No implica despliegue ni aceptación en producción.

## Operación

1. Seleccionar el Excel calcula SHA-256 sobre los bytes originales, antes de
   leer encabezados. El nombre del archivo no interviene en la identidad.
2. Si existe una carga confirmada visible con esa huella, el asistente muestra
   archivo, fecha snapshot, fecha/hora de procesamiento, usuario, resumen y
   estado. Previsualizar queda deshabilitado; una llamada directa también queda
   bloqueada antes de crear `licitacion.carga`.
3. Si hay varias coincidencias, aparecen todas en una lista con acceso al
   formulario. Un selector permite consultar los datos de cada una.
4. «Forzar re-importación (avanzado)» abre otro asistente con motivo obligatorio
   y casilla de confirmación explícita. Continúa al preview habitual y registra
   usuario, motivo, SHA y cargas anteriores en el chatter de la nueva carga.
5. Cancelar no crea una carga nueva. Los asistentes temporales siguen el ciclo
   de limpieza nativo de Odoo.

El mismo tratamiento aplica al catálogo SAI. Un archivo con bytes distintos,
aunque contenga los mismos datos, se permite y puede producir cero cambios.
Borradores, previews pendientes y cargas pendientes de asignación no bloquean
otra subida. La confirmación vuelve a comprobar las coincidencias para cubrir
una carga que se haya confirmado mientras el usuario tenía abierto el preview.

«Procesado el» usa la fecha real de confirmación y su usuario para las cargas
nuevas. Para registros históricos utiliza `create_date` y `user_id/create_uid`:
no se inventa una fecha de confirmación que antes no se guardaba. Odoo presenta
las fechas y horas con el idioma y zona horaria del usuario.

## Historial y decisiones del borrador

`binary_sha256` es calculado, almacenado, indexado y no editable. Al incorporar
la columna, la recomputación almacenada de Odoo obtiene las huellas de los
adjuntos históricos. No cambia estados, resúmenes, snapshots ni metadatos de
escritura de esas cargas. La columna es opcional y está oculta inicialmente en
la lista; el formulario muestra la huella y señala coincidencias históricas.

Se conservan todos los duplicados anteriores. La reconciliación que dejaría
una sola carga confirmada permanece pendiente de decisión del cliente: modificar
estados históricos contradice la retención actual y requiere elegir el registro
canónico. Las reimportaciones forzadas son nuevas versiones intencionales.

Por ese motivo no se instala el `EXCLUDE` propuesto en el borrador: también
rechazaría las reimportaciones forzadas y los duplicados existentes. En su lugar:

- El asistente conserva el resultado por archivo, nombre, fecha, alcance,
  origen, zona horaria y empresas; un reintento del mismo asistente reutiliza
  la carga creada.
- Confirmar una carga ya confirmada devuelve éxito sin repetir el commit.
- Una tabla interna, con SHA único, serializa mediante una escritura real las
  operaciones sobre el mismo binario. Ante un snapshot concurrente obsoleto,
  PostgreSQL produce un conflicto de serialización y el RPC de Odoo se reintenta.
  Esto evita depender solo de un bloqueo asesor bajo `REPEATABLE READ`.
- El servidor genera los campos de fuerza y de resultado previo. El contexto
  RPC no permite inyectar esos valores. Cambiar el archivo o alcance invalida
  una confirmación avanzada que ya había sido guardada.

La consulta respeta reglas multiempresa y no expone coincidencias de empresas
no autorizadas. La barrera transaccional global no devuelve datos de esas cargas.
Dos ámbitos sin acceso mutuo pueden conservar su propia carga; la protección
de identidad global de procedimientos permanece vigente.

La selección de una carga anterior comprueba permisos en `create`, `write` y
`onchange`, con el usuario original, incluyendo los valores por defecto del
contexto. En Odoo 19 las restricciones `@api.constrains` se ejecutan con `sudo`;
se reservan aquí para comprobar que la carga corresponde al archivo, y no para
autorizar el acceso. Véase [implementación de `_validate_fields`](https://github.com/odoo/odoo/blob/19.0/odoo/orm/models.py).

Referencias técnicas: [reintentos RPC de Odoo 19](https://github.com/odoo/odoo/blob/19.0/odoo/service/model.py)
y [aislamiento de transacciones PostgreSQL](https://www.postgresql.org/docs/15/transaction-iso.html).

## Referencia del diff

La última carga confirmada se obtiene por origen, alcance, tipo, procedimiento
y conjunto de empresas, ordenada por fecha snapshot e ID. Cambiar el nombre
diario de la exportación no rompe esta referencia. El preview la muestra.

Los valores se comparan contra los registros actuales, incluso si no hay carga
anterior; las ausencias se calculan desde la carga confirmada de referencia.
Si no existe esa carga, aparece una advertencia explícita y no se marcan
ausencias. Si existe pero sus registros ya no están disponibles, se detiene
el proceso en vez de aceptar un baseline vacío.

«Nuevos: 30» en una primera carga no demuestra por sí solo un error. Se añadieron
pruebas para evitar clasificar como nuevos procedimientos que ya existen; no
se reescriben resúmenes históricos sin evidencia de qué ocurrió en cada carga.

## Verificación y actualización

- Cuatro pruebas independientes verifican hash de bytes originales, base64
  inválido/vacío y límite de tamaño.
- `TestFileDuplicates` agrega dieciséis pruebas ORM: bloqueo antes del parser,
  archivos renombrados/editados, múltiples coincidencias, fuerza y auditoría,
  doble envío, cargas pendientes, catálogo, empresas, contexto RPC, huellas
  históricas y transacciones PostgreSQL con snapshot obsoleto.
- Los tests anteriores de idempotencia de contenido usan explícitamente la
  reimportación forzada cuando reutilizan exactamente el mismo binario.
- El script de operaciones `ops/actualizar_licitaciones_dev_qa.sh`, en el
  workspace BIOTECH, publica únicamente la rama QA y exige las pruebas DEV-03
  además de las de DEV-01/02 antes de aplicar la actualización.
- El actualizador conserva respaldo y recuperación. Antes de habilitar el
  servicio verifica que todas las cargas confirmadas tengan una huella válida;
  un adjunto histórico ausente que impida obtenerla requiere revisión.
- No hay migración de limpieza de duplicados ni cambio de catálogos semilla.

La ejecución ORM, PDF/XLSX, concurrencia real y revisión visual en Odoo se
validarán en el ensayo del servidor. Las comprobaciones locales por sí solas
no certifican esa ejecución ni cobertura global del 80 %.

El ensayo de `a02ff1c` ejecutó 64 pruebas y reportó un fallo, cero errores:
la selección de una carga ajena no produjo el `AccessError` esperado por el
motivo descrito arriba. La instalación de QA no llegó a iniciarse. La versión
`19.0.3.0.1` corrige esa autorización y amplía las comprobaciones de selección
permitida y denegada; requiere repetir el ensayo completo.
