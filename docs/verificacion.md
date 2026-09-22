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
