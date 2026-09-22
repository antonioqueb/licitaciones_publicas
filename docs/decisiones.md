# Validación del brief · 21/09/2026

Prevalece la sección 16. Empresas existentes en `res.company`; ningún dato de
demo crea razones sociales o proveedores del cliente. Solo backend, archivos
manuales, sin integraciones contables ni firma electrónica.

## Ajustes técnicos

- Odoo 19: `models.Constraint`, `res.groups.privilege`, vistas `list`, expresiones
  directas `readonly`, `invisible` y `required`; no `attrs` ni `tree` antiguos.
- `report_xlsx` OCA 19.0 es una dependencia explícita. Se omite `documents`: A-03
  dispone adjuntos y no se usa su API. No necesita Enterprise para almacenar archivos.
- `ir.attachment` usa el parámetro nativo `ir_attachment.location=file` y el
  `data_dir` del servidor. No existe un campo estándar `storage='fs'` que habilite
  NFS/S3/SharePoint. La migración necesita un adaptador y una ubicación definidos.
- Se usa normalización Unicode estándar (NFKD) para encabezados en español;
  no es necesaria la dependencia `unidecode`.
- No se borran procedimientos, partidas, cargas, apariciones, expedientes ni
  documentos ni siquiera como administrador. Se permite retirar asignaciones,
  con trazabilidad. Los catálogos se archivan.
- El preview no crea catálogos ni registros destino. El diff confirmado debe
  coincidir con el recalculado; una previsualización obsoleta se rechaza.
- La ausencia se compara contra la carga anterior del mismo origen, alcance,
  tipo, procedimiento y conjunto de empresas activas. El usuario debe mantener
  el mismo alcance para exportaciones con los mismos filtros.
- Las fechas del Excel sin zona se interpretan en America/Mexico_City,
  configurable en cada carga, y se almacenan en UTC.
- `margen_pct = (precio - costo) / precio * 100`. El recargo secundario se
  compara con ese margen de la línea principal. Se requiere costear primero la
  principal; el sugerido siempre supera su margen. No modifica automáticamente
  el precio unitario. No se revela el costeo de otras empresas no autorizadas.

## Decisiones pendientes

- Los documentos, 8 mockups y 3 Excel mencionados no se encontraron en BIOTECH,
  Client Odoo ni Downloads durante la revisión inicial. Se solicitó su ubicación.
- El listado oficial se considera pendiente según 16.2, aunque 2/12/14 hablan
  de una muestra de 117 registros. Las pruebas sintéticas no la sustituyen.
- 16.3.10 es contradictoria. Interpretación provisional consultada: una nueva
  carga con fechas límite cambiadas habilita una criba manual para retomar un
  descartado. La importación nunca cambia el estado interno.
- Ubicación final y retención documental (S4), uso de firma escaneada (S5).
- No hay runtime Odoo disponible: Docker denegado por sandbox, PostgreSQL sin
  servicio, código Odoo ausente y descarga por shell sin DNS. La instalación,
  pruebas ORM/PDF, cobertura completa y capturas reales requieren ese entorno.

Referencias técnicas: [ORM Odoo 19](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html),
[grupos Odoo 19](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_groups.py),
[adjuntos](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/ir_attachment.py),
[OCA report_xlsx](https://github.com/OCA/reporting-engine/tree/19.0/report_xlsx).
