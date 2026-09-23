# DEV-01 / DEV-02 — Implementación para QA

Rama: `qa/dev01-dev02-importacion`. Versión: `19.0.2.0.2`.
Estos cambios no se publican en `main` ni se aplican a producción.

## Catálogos

Configuración incluye Tipos de archivo, Prefijos de procedimiento, Claves de
carácter y Partidas SAI. Usuarios de licitaciones tienen lectura; administradores
pueden configurar. Se conservan los registros: no se permite borrarlos.

Se cargan los seis tipos solicitados, cuatro prefijos LA/IA/LI/LO y tres claves
N/I/T. Sus descripciones son «Por definir por cliente». Los datos semilla tienen
`noupdate=1`: actualizar el módulo conserva la configuración del cliente.
El despliegue inicial creó estos catálogos sobre QA `7cbee6d` (19.0.1.0.1).
QA `25a4fce` (19.0.2.0.1) ya completó 48 pruebas de Odoo sin fallos ni errores
y se instaló según la evidencia del release `licitaciones-dev-20260922T215618917490Z`.

La versión 19.0.2.0.2 añade el tipo de contratación «Servicios relacionados con
la obra», código interno `SRO`, observado en el listado del cliente. Admite
también «Servicios relacionados con la obra pública», sin diferencias de
acentos, mayúsculas o espacios. Mantiene separados `SER` y `OBR`; no deduce una
clave del identificador. El nuevo registro semilla se incorpora al actualizar
el módulo, conservando los catálogos ya configurados. Su prueba ORM recorre
previsualización, confirmación, snapshot y segunda carga sin cambios.

`licitacion.tipo.archivo` contiene todos los campos DEV-01. Se añade
`mapeo_columnas` (JSON) para definir qué campo de destino corresponde a cada
encabezado. Cambiar nombres de columnas no requiere modificar Python. Ejemplo:

```json
{"identificador": ["NÚMERO DE IDENTIFICACIÓN", "Número de procedimiento"],
 "nombre_publicado": ["Nombre publicado"],
 "unidad_nombre": ["Unidad compradora"],
 "estatus": ["Estatus"],
 "tipo_codigo": ["Tipo de contratación"],
 "entidad_nombre": ["Entidad federativa"]}
```

Solo se permiten campos técnicos conocidos. No se admite `state`, expresiones,
SQL ni código. Se valida JSON y se rechazan alias ambiguos.

## Detección y validación

1. Consultar formatos activos, con prioridad `secuencia` ascendente.
2. Usar la hoja y fila configuradas. `hoja_nombre` vacío indica primera hoja.
3. Comparar glob de nombre (varios separados por comas) y palabras clave del
   encabezado. Las palabras configuradas deben estar presentes; el nombre por
   sí solo no permite saltarse las validaciones estructurales.
4. Validar número de hojas y columnas. Para servicios se configura la alternativa
   de siete columnas mediante `{"cols": [...], "columnas_alternativas": [7]}`.
5. Exigir coincidencia de al menos 70% de los nombres de `cols`. El orden de
   columnas no importa. Sin `cols`, esa comprobación se omite; no se inventan
   encabezados ausentes de la especificación.
6. Para detalles: mínimo y máximo presentes → rangos, cantidad solicitada →
   bienes, sin cantidad → servicios. Esto no depende de N/I/T ni del nombre.
7. Entre formatos compatibles prevalece la prioridad menor. A igual prioridad,
   se favorece el patrón de nombre coincidente y después el código técnico.

Normalización: Unicode NFKD sin acentos, mayúsculas, espacios normalizados y
signos neutralizados. Para encabezados en español equivale a la normalización
solicitada, conservando compatibilidad con `Núm.` y `Clave CUCoP+`; no requiere
reconstruir las imágenes de Odoo para añadir una biblioteca.

No existe un fallback de formatos codificados en el lector: utiliza la
configuración del catálogo. Los procesadores mantienen validaciones de tipos
y campos destino obligatorios. Se conservan los límites de 25 MB y 50,000 filas.

## Identificadores e incidencias

En `LA-50-GYR-050GYR032-N-89-2026`, el prefijo es LA y la clave N está en el
quinto segmento (tercero desde la derecha). Se sigue el ejemplo de la
especificación; «posición 3» no corresponde al tercer segmento desde la izquierda.

El lector valida estructura; el adaptador valida prefijo activo y clave contra
los catálogos. No interpreta sus significados ni deduce legislación. Se conserva
el campo de ordenamiento histórico existente, pero no se calcula para altas nuevas.

Una fila de listado con identificador no catalogado queda en la carga original
y genera una incidencia bloqueante al confirmar. No se crea un procedimiento
inválido. La incidencia puede pertenecer a la carga sin procedimiento todavía;
su acceso depende de las empresas de esa carga. Tras completar el catálogo y
resolver con nota, se vuelve a importar para crear las filas pendientes.

Detalle: partida ausente en SAI → bloqueante; relación CUCoP+ incompatible →
advertencia; identificador del nombre/contenido/padre diferente → advertencia.
No se compara N/I/T con bienes o servicios ni se cambia la contratación a partir
de las unidades de las partidas. Las incidencias de catálogo solo se resuelven
después de completar el catálogo, con nota.

## Preview y trazabilidad

Todos los tipos importables, incluido el catálogo SAI, requieren preview y
confirmación. Se conservan los cuatro bloques, el Excel original y la
configuración utilizada. Cambiar configuración, identificadores o relaciones SAI
después del preview invalida la confirmación; se debe volver a previsualizar.

Los catálogos y registros destino no se crean al previsualizar. La confirmación
mantiene una única transacción y la clave MD5 de la terna de la partida.
Se conserva el estado interno, las asignaciones y los expedientes.

## Listado oficial: encabezados recibidos el 22/09/2026

El perfil semilla valida las 13 columnas proporcionadas por el cliente. El
mapeo sigue siendo configurable desde el catálogo:

| Encabezado | Destino |
| --- | --- |
| NÚM. | `numero_listado` (entero, consecutivo del último listado) |
| NÚMERO DE IDENTIFICACIÓN | `identificador` |
| CARÁCTER | `caracter_publicado` (texto literal, independiente de la clave del identificador) |
| NOMBRE | `nombre_publicado` |
| SIGLAS DEPENDENCIA O ENTIDAD | `siglas_dependencia` |
| ESTATUS | `estatus_portal_id` |
| FECHA JUNTA DE ACLARACIONES | `fecha_junta_aclaraciones`, admite vacío |
| FECHA DE PRESENTACIÓN Y APERTURA DE PROPOSICIONES | `fecha_apertura` |
| TIPO DE PUBLICACIÓN | `tipo_publicacion` (texto literal) |
| TIPO DE CONTRATACIÓN | `tipo_contratacion_id` |
| CÓDIGO DE EXPEDIENTE | `codigo_expediente` |
| UNIDAD COMPRADORA | `unidad_compradora_id` |
| ENTIDAD FEDERATIVA | `entidad_id` de la unidad compradora |

Los datos adicionales del portal se muestran en «Datos del listado» y solo los
modifica una importación confirmada. También quedan en el snapshot de la carga.
Las fechas de texto admiten `dd/mm/yyyy HH:MM`, segundos opcionales, fecha sin
hora y formatos ISO de fecha con hora separada por espacio. Se convierten de la
zona horaria declarada a UTC. Recibir los encabezados no equivale a haber probado
el Excel original del cliente: los ejemplos de filas de las pruebas son sintéticos.

## Detalle en borrador y pendientes del cliente

- Se muestra **BORRADOR - Pendiente validación cliente** en tipo de archivo,
  carga y preview de detalles.
- Ante servicios sin cantidad, el criterio provisional es «Cantidad pendiente».
  El valor técnico cero no se interpreta como cantidad contratada: se bloquea
  crear costeo y publicar el expediente mientras falte confirmar la cantidad.
  Una nueva carga con cantidad informada puede completar el renglón.
- Rango mínimo = máximo conserva ambos valores y el subtipo rangos.
- `licitacion.clave.sai.code` identifica la partida específica; `cucop_ids`
  contiene sus claves permitidas. `Libro1.xlsx` se procesa por separado, solo
  por administradores, con preview. No se borran ni se desactivan partidas por
  ausencia en una carga del catálogo.
- **No se recibió el catálogo SAI real.** No se siembran relaciones inventadas.
  Mientras falten, los detalles generan incidencias de partida no catalogada.
- **Faltan los 10 encabezados exactos de SAI y el Excel original del listado.**
  Los 13 encabezados del listado ya se incorporaron; sigue pendiente comprobar
  las 117 filas reales, sus fechas y valores de catálogo.
- La fila 2 del detalle 034 y cualquier hoja distinta se deben configurar como
  un perfil adicional (código único, patrón específico, prioridad adecuada).
  Ya no se adivina la fila recorriendo las primeras cinco.
- Anexo técnico queda registrado y se reconoce su estructura. Su procesamiento
  de negocio no se incluye en DEV-02 y devuelve un mensaje explícito.

## Validación

Las pruebas standalone ejercitan configuración, normalización, prioridad,
umbral exacto del 70%, hojas/filas, subtipos, rangos y ausencia de cantidades.
Las pruebas ORM incluyen configuración inválida, datos semilla, incidencias sin
procedimiento, SAI, cambios posteriores al preview, acceso por empresa y costeo.
El despliegue QA ejecuta estas pruebas en un contenedor Enterprise aislado antes
de actualizar únicamente QA. La aceptación con archivos reales sigue pendiente.
