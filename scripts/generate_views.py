"""Generate native Odoo 19 views. Re-run after changing this source."""
from generate_data import write


def view(xmlid, model, arch):
    return f'<record id="{xmlid}" model="ir.ui.view"><field name="name">{xmlid}</field><field name="model">{model}</field><field name="arch" type="xml">{arch}</field></record>\n'


def action(xmlid, name, model, modes='list,form', extra=''):
    return f'<record id="{xmlid}" model="ir.actions.act_window"><field name="name">{name}</field><field name="res_model">{model}</field><field name="view_mode">{modes}</field>{extra}</record>\n'


def field(name, extra=''):
    return f'<field name="{name}" {extra}/>'


def fields(names):
    return ''.join(field(n) for n in names.split())


def button(name, label, extra=''):
    return f'<button name="{name}" string="{label}" type="object" {extra}/>'


def wizard(name, label, body, method):
    return view('view_' + name.replace('.', '_'), 'licitacion.' + name,
                f'<form string="{label}">{body}<footer>' + button(method, label, 'class="btn-primary"') + '<button string="Cancelar" special="cancel"/></footer></form>')


def save(path, content):
    write(path, '<odoo>\n' + content + '\n</odoo>')


def draft_banner():
    return '<field name="detalle_borrador" invisible="1"/><div class="alert alert-warning" role="alert" invisible="not detalle_borrador">BORRADOR - Pendiente validación cliente. Revise las cantidades y las incidencias SAI antes de continuar.</div>'


def generate():
    matches = '''<field name="cargas_previas_ids" readonly="1" nolabel="1"><list create="0" edit="0" delete="0">
<field name="archivo_nombre"/><field name="fecha_snapshot"/><field name="procesado_el"/><field name="procesado_por_id"/>
<field name="resumen"/><field name="state"/><button name="action_open" string="Abrir" type="object"/>
</list></field>'''
    upload = '<form string="Nueva carga">' + draft_banner() + '<group>' + field('archivo_nombre', 'invisible="1"') + field('archivo', 'filename="archivo_nombre"') + fields('fecha_snapshot tipo_detectado origen_portal alcance zona_horaria') + '''</group>
<div class="alert alert-warning" role="alert" invisible="not cargas_previas_ids">
<strong>El archivo «<field name="archivo_nombre" readonly="1" nolabel="1"/>» ya fue procesado.</strong>
<p>Consulte la carga anterior. Para procesarlo nuevamente debe indicar un motivo y confirmar la reimportación.</p>
<group><field name="carga_previa_id" domain="[('id','in',cargas_previas_ids)]" options="{'no_create': True, 'no_create_edit': True}"/>
<field name="previa_snapshot"/><field name="previa_procesada"/><field name="previa_usuario_id"/><field name="previa_resumen"/><field name="previa_state"/></group>
''' + matches + '''</div><p>Declare la fecha de descarga. Ningún procedimiento o partida cambia antes de confirmar la previsualización.</p>
<footer><button name="action_preview" string="Previsualizar cambios" type="object" class="btn-primary" invisible="cargas_previas_ids"/>
<span class="btn btn-primary disabled" role="button" aria-disabled="true" invisible="not cargas_previas_ids">Previsualizar cambios</span>
<button name="action_open_existing" string="Abrir carga existente" type="object" invisible="not cargas_previas_ids"/>
<button string="Cancelar" special="cancel"/>
<button name="action_force" string="Forzar re-importación (avanzado)" type="object" invisible="not cargas_previas_ids"/>
</footer></form>'''
    w = view('view_carga_wizard', 'licitacion.carga.wizard', upload)
    w += action('action_carga_wizard', 'Nueva carga', 'licitacion.carga.wizard', 'form', '<field name="target">new</field>')
    w += wizard('forzar.carga.wizard', 'Confirmar reimportación', '<p>Se creará una nueva carga del mismo archivo. Las anteriores se conservarán.</p><group>' + fields('carga_wizard_id motivo') + field('confirmado', 'required="1"') + '</group>', 'action_confirm')
    w += wizard('asignar.procedimiento.wizard', 'Asignar y previsualizar', '<group>' + fields('carga_id procedimiento_id nota') + '</group>', 'action_asignar')
    preview = '<form string="Previsualización">' + draft_banner() + '<group>' + fields('carga_id resumen carga_base_id') + '</group><div class="alert alert-info" role="status" invisible="not aviso_base">' + field('aviso_base', 'nolabel="1"') + '</div><div class="alert alert-warning" role="alert" invisible="not advertencias">' + field('advertencias') + '</div><notebook>'
    for key, label in [('nuevos', 'Nuevos'), ('cambios', 'Cambios'), ('sin_cambios', 'Sin cambios'), ('gone', 'Ya no aparecen')]:
        preview += f'<page string="{label}"><field name="{key}_ids"><list create="0" edit="0" delete="0">' + fields('clave descripcion detalle') + '</list><form><group>' + fields('clave descripcion detalle') + '</group></form></field></page>'
    preview += '</notebook><footer>' + button('action_confirm', 'Confirmar importación', 'class="btn-primary"') + button('action_rechazar', 'Rechazar carga') + '<button string="Cerrar" special="cancel"/></footer></form>'
    w += view('view_preview', 'licitacion.preview.wizard', preview)
    w += wizard('criba.wizard', 'Aplicar decisión', '<group>' + field('procedimiento_ids', 'widget="many2many_tags"') + fields('es_lote decision') + field('motivo_id', "invisible=\"decision not in ('descartar','no_viable')\" required=\"decision in ('descartar','no_viable')\"") + field('nota') + '</group>', 'action_apply')
    w += wizard('generar.expedientes.wizard', 'Generar expedientes', '<group>' + fields('procedimiento_id resumen') + '</group><p>Un expediente por empresa y una carta por proveedor. Se conservarán los existentes.</p>', 'action_generate')
    correction = '<group>' + fields('incidencia_id decision') + field('es_catalogo', 'invisible="1"') + field('campo', 'invisible="1"')
    correction += field('valor_encontrado', 'invisible="not es_catalogo"')
    for key in ('entidad_federativa', 'estatus_portal', 'tipo_contratacion', 'tipo_procedimiento', 'caracter_procedimiento', 'unidad_compradora'):
        condition = f"es_catalogo and decision == 'resolver' and campo == '{key}'"
        correction += field(key + '_id', f'invisible="not ({condition})" required="{condition}" options="{{\'no_create\': True}}"')
    correction += field('guardar_alias', "invisible=\"not es_catalogo or decision != 'resolver' or campo != 'entidad_federativa'\"")
    correction += '<div class="alert alert-info" invisible="not es_catalogo or decision != \'resolver\' or campo == \'entidad_federativa\'">Revise el catálogo y sus nombres alternativos, si los admite. Esta corrección asigna el registro seleccionado sin agregar alias automáticamente.</div>'
    correction += field('nota') + '</group>'
    w += wizard('resolver.incidencia.wizard', 'Aplicar resolución', correction, 'action_apply')
    for what in ('empresas', 'proveedores'):
        w += wizard(f'propagar.{what}.wizard', f'Propagar {what}', '<group>' + field('partida_ids', 'widget="many2many_tags"') + field('fuente_id', "domain=\"[('id','in',partida_ids)]\"") + '</group><p>La selección fuente reemplazará las asignaciones de las otras partidas.</p>', 'action_apply')
    save('wizards/wizard_views.xml', w)

    p = view('view_procedimiento_list', 'licitacion.procedimiento', '''<list decoration-warning="junta_class == 'urgente'" decoration-danger="junta_class == 'vencida'" decoration-muted="not sigue_apareciendo">
<field name="identificador"/><field name="nombre_publicado" class="lp_truncate"/><field name="unidad_compradora_id"/><field name="entidad_id" optional="show"/><field name="fecha_junta_aclaraciones"/><field name="junta_class" widget="badge"/><field name="state" widget="badge"/><field name="estatus_portal_id"/><field name="company_ids" widget="many2many_tags" optional="show"/><field name="sigue_apareciendo" optional="hide"/><field name="user_id" widget="many2one_avatar_user"/><button name="action_cribar" string="Cribar" type="object"/></list>''')
    p += view('view_procedimiento_kanban', 'licitacion.procedimiento', '''<kanban default_group_by="state" records_draggable="0" quick_create="0"><field name="junta_class"/><field name="state"/><field name="nombre_publicado"/>
<progressbar field="junta_class" colors='{"normal":"success","urgente":"warning","vencida":"danger","sin_fecha":"secondary"}'/>
<templates><t t-name="card"><strong><field name="identificador"/></strong><div class="lp_truncate" t-att-title="record.nombre_publicado.value"><field name="nombre_publicado"/></div><field name="unidad_compradora_id"/><div><field name="fecha_junta_aclaraciones"/><field name="junta_class" widget="badge"/></div><footer><button name="action_cribar" type="object" class="btn btn-secondary">Cribar</button><field name="user_id" widget="many2one_avatar_user"/></footer></t></templates></kanban>''')
    p += view('view_procedimiento_search', 'licitacion.procedimiento', '''<search><field name="identificador"/><field name="nombre_publicado"/><field name="unidad_compradora_id"/><filter name="relevantes" string="Solo relevantes" domain="[('state','not in',['descartado','no_viable','con_fallo'])]"/><filter name="ausentes" string="Ya no aparecen" domain="[('sigue_apareciendo','=',False)]"/><filter name="mis_procedimientos" string="Mis procedimientos" domain="[('user_id','=',uid)]"/><filter name="archivados" string="Archivados" domain="[('active','=',False)]"/><group><filter name="por_estado" string="Estado interno" context="{'group_by':'state'}"/><filter name="por_entidad" string="Entidad" context="{'group_by':'entidad_id'}"/><filter name="por_uc" string="Unidad compradora" context="{'group_by':'unidad_compradora_id'}"/></group><searchpanel><field name="entidad_id"/><field name="tipo_contratacion_id"/><field name="unidad_compradora_id"/></searchpanel></search>''')
    p += view('view_procedimiento_form', 'licitacion.procedimiento', '''<form><header><button name="action_cribar" string="Cribar" type="object" class="btn-primary"/><button name="action_pasar_a_analisis" string="Confirmar En análisis" type="object" invisible="state != 'detectado'"/><button name="action_generar_expedientes" string="Generar expedientes" type="object" invisible="state not in ('analisis','preguntas')"/><button name="action_avanzar" string="Siguiente etapa" type="object" invisible="state not in ('preguntas','costeo','propuesta')"/><field name="state" widget="statusbar" statusbar_visible="detectado,analisis,preguntas,costeo,propuesta,con_fallo"/></header>
<sheet><div class="oe_button_box" name="button_box"><button type="object" name="action_open_expedientes" class="oe_stat_button" icon="fa-folder-open"><div class="o_stat_info"><span class="o_stat_text">Expedientes</span></div></button><button type="object" name="action_open_incidencias" class="oe_stat_button" icon="fa-exclamation-triangle"><field name="incidencias_abiertas_count" widget="statinfo" string="Incidencias"/></button></div><field name="active" invisible="1"/>
<h1><field name="identificador"/></h1><field name="nombre_publicado"/><group><group><field name="unidad_compradora_id"/><field name="entidad_id"/><field name="tipo_contratacion_id"/><field name="codigo_expediente"/><field name="user_id"/><field name="estatus_portal_id"/></group><group><field name="tipo_procedimiento"/><field name="tipo_procedimiento_id"/><field name="caracter"/><field name="caracter_procedimiento_id"/><field name="ordenamiento_legal" invisible="not ordenamiento_legal"/><field name="ejercicio"/><field name="company_ids" widget="many2many_tags"/><field name="sigue_apareciendo"/><field name="fecha_ya_no_aparece" invisible="sigue_apareciendo"/></group></group>
<notebook><page string="Fechas fatales"><group><field name="fecha_junta_aclaraciones"/><field name="fecha_limite_preguntas"/><field name="fecha_entrega_muestras"/><field name="fecha_apertura"/><field name="fecha_fallo"/><field name="fecha_fallo_original"/><field name="fallo_diferido"/></group></page>
<page string="Datos del listado"><group><field name="numero_listado"/><field name="caracter_publicado"/><field name="siglas_dependencia"/><field name="tipo_publicacion"/></group><p>Valores publicados en el último listado confirmado. El carácter publicado no cambia las descripciones del catálogo de identificadores.</p></page>
<page string="Renglones"><div class="alert alert-info" role="status" invisible="state != 'detectado'">Confirma «En análisis» para editar partidas.</div><div class="lp_steps"><span>1 · Confirmar análisis</span><span>2 · Asignar empresas</span><span>3 · Asignar proveedores</span><span>4 · Generar expedientes</span></div><group><field name="renglones_count"/><field name="renglones_con_empresa_count"/><field name="renglones_descartados_count"/></group><field name="partida_ids" context="{'default_procedimiento_id':id}" readonly="state in ('detectado','descartado','no_viable','con_fallo')"><list><field name="numero"/><field name="clave_cucop"/><field name="descripcion_detallada" class="lp_truncate"/><field name="unidad_medida"/><field name="cantidad" invisible="cantidad_pendiente"/><field name="cantidad_pendiente"/><field name="company_ids" widget="partida_empresas_chips"/><field name="empresa_principal_id" optional="hide"/><field name="participacion" widget="badge"/><field name="motivo_descarte_id"/><field name="sigue_apareciendo" optional="hide"/></list></field></page>
<page string="Criba"><group><field name="motivo_descarte_id" readonly="1"/><field name="nota_criba" readonly="1"/><field name="reapertura_habilitada"/></group></page><page string="Historial"><field name="aparicion_ids" readonly="1"><list create="0" delete="0"><field name="carga_id"/><field name="presente"/><field name="nombre_publicado_snapshot"/><field name="estatus_portal_id_snapshot"/><field name="fecha_junta_snapshot"/></list></field></page></notebook></sheet><chatter/></form>''')
    p += action('action_procedimientos', 'Procedimientos', 'licitacion.procedimiento', 'list,kanban,form')
    p += server_action('action_criba_lote', 'Cribar en lote', 'procedimiento', 'action_cribar')
    save('views/procedimiento_views.xml', p)

    p = view('view_partida_list', 'licitacion.partida', '<list>' + fields('procedimiento_id numero clave_cucop descripcion_detallada cantidad cantidad_pendiente') + field('company_ids', 'widget="partida_empresas_chips"') + field('empresa_principal_id', 'optional="hide"') + field('participacion') + '</list>')
    p += view('view_partida_form', 'licitacion.partida', '''<form><header><button name="action_reabrir" string="Reabrir decisión de partida" type="object" invisible="participacion != 'descartada'"/><field name="participacion" widget="statusbar"/></header><sheet><group><field name="procedimiento_id"/><field name="importada" invisible="1"/><field name="numero" readonly="importada"/><field name="partida_especifica" readonly="importada"/><field name="clave_cucop" readonly="importada"/><field name="descripcion_cucop" readonly="importada"/><field name="descripcion_detallada" readonly="importada"/><field name="unidad_medida" readonly="importada"/><field name="cantidad_pendiente"/><field name="cantidad" readonly="importada" invisible="cantidad_pendiente"/><field name="cantidad_min" readonly="importada"/><field name="cantidad_max" readonly="importada"/></group><group string="Empresas participantes"><field name="company_ids" widget="partida_empresas_chips"/><field name="empresa_principal_id" invisible="1"/><field name="partida_empresa_ids" context="{'default_partida_id':id}"><list editable="bottom"><field name="sequence" widget="handle"/><field name="company_id"/><field name="rol" widget="badge" decoration-success="rol == 'principal'" decoration-warning="rol == 'secundaria'"/><field name="nota"/></list></field></group><group string="Proveedores"><field name="proveedor_sugerido_ids" widget="many2many_tags"/><field name="partida_proveedor_ids" context="{'default_partida_id':id}"><list editable="bottom"><field name="partner_id"/><field name="fecha_asignacion"/></list></field></group><group string="Descarte"><field name="motivo_descarte_id" domain="[('aplica_a','in',['partida','ambos'])]"/><field name="nota_descarte"/></group></sheet><chatter/></form>''')
    for what in ('empresas', 'proveedores'):
        p += server_action('action_propagar_' + what, 'Propagar ' + what, 'partida', 'action_propagar_' + what)
    p += action('action_partidas', 'Renglones', 'licitacion.partida')
    save('views/partida_views.xml', p)

    e = view('view_expediente_list', 'licitacion.expediente', '<list>' + fields('folio procedimiento_id company_id partidas_count proveedores_count preguntas_count total_costo total_precio margen_pct state') + field('currency_id', 'column_invisible="True"') + '</list>')
    e += view('view_expediente_form', 'licitacion.expediente', '''<form><header><button name="action_armar" string="Comenzar armado" type="object" invisible="state != 'borrador'"/><button name="action_listo" string="Marcar listo" type="object" invisible="state != 'en_armado'"/><button name="action_publicar" string="Publicar propuesta" type="object" class="btn-primary" invisible="state != 'listo' or bloqueantes_pendientes"/><button name="action_print_cartas_zip" string="Descargar cartas ZIP" type="object"/><field name="state" widget="statusbar"/></header><sheet><h1><field name="folio"/></h1><group><field name="procedimiento_id"/><field name="company_id"/><field name="active" invisible="1"/><field name="currency_id" invisible="1"/></group><div class="alert alert-warning" role="alert" invisible="not bloqueantes_pendientes"><field name="bloqueantes_pendientes"/></div><notebook>
<page string="Preguntas"><field name="partida_ids" invisible="1"/><field name="pregunta_ids" context="{'default_expediente_id':id}"><list editable="bottom"><field name="sequence" widget="handle"/><field name="partida_id" domain="[('id','in',parent.partida_ids)]"/><field name="texto"/><field name="autor_id"/><field name="state"/><field name="respuesta_portal"/></list></field></page>
<page string="Costeo"><group><field name="total_costo"/><field name="total_precio"/><field name="margen_bruto"/><field name="margen_pct"/></group><field name="costeo_linea_ids" context="{'default_expediente_id':id}"><list editable="bottom"><field name="partida_id" domain="[('id','in',parent.partida_ids)]"/><field name="proveedor_id"/><field name="cantidad"/><field name="costo_unitario"/><field name="precio_unitario"/><field name="total_costo" sum="Costo"/><field name="total_precio" sum="Precio"/><field name="margen_pct"/><field name="es_secundaria" column_invisible="True"/><field name="recargo_secundaria_pct" readonly="not es_secundaria"/><field name="currency_id" column_invisible="True"/></list></field></page>
<page string="Docs proveedores"><field name="documento_proveedor_ids" context="{'default_expediente_id':id,'default_tipo':'prov_ficha'}"><list><field name="partner_id"/><field name="partida_id"/><field name="tipo"/><field name="state"/><field name="fecha_vencimiento"/><field name="bloqueante"/></list></field></page>
<page string="Docs propios"><field name="documento_propio_ids" context="{'default_expediente_id':id,'default_tipo':'propio_otro'}"><list><field name="tipo"/><field name="state"/><field name="monto"/><field name="fecha_vencimiento"/><field name="bloqueante"/><field name="currency_id" column_invisible="True"/></list></field></page>
<page string="Resumen"><group><field name="partidas_count"/><field name="proveedores_count"/><field name="preguntas_count"/><field name="total_costo"/><field name="total_precio"/><field name="margen_pct"/></group><field name="carta_apoyo_ids" readonly="1"><list><field name="folio"/><field name="partner_id"/><field name="state"/><button name="action_print_carta" string="PDF" type="object"/><button name="action_enviar" string="Enviar al proveedor" type="object" invisible="state != 'borrador'" confirm="Se enviará un correo al proveedor. ¿Continuar?"/></list></field></page></notebook></sheet><chatter/></form>''')
    e += view('view_documento_form', 'licitacion.documento', '<form><sheet><group>' + fields('expediente_id tipo partner_id partida_id state fecha_recepcion fecha_vencimiento monto bloqueante nota') + field('currency_id', 'invisible="1"') + field('archivo_nombre', 'invisible="1"') + field('archivo', 'filename="archivo_nombre"') + '</group><group string="Versiones conservadas"><field name="version_ids" readonly="1"><list create="0" edit="0" delete="0"><field name="create_date"/><field name="user_id"/><field name="archivo_nombre"/><field name="archivo" filename="archivo_nombre"/></list></field></group></sheet><chatter/></form>')
    e += view('view_carta_form', 'licitacion.carta.apoyo', '<form><header>' + button('action_print_carta', 'Descargar PDF') + button('action_enviar', 'Enviar al proveedor', "invisible=\"state != 'borrador'\" confirm=\"Se enviará un correo al proveedor. ¿Continuar?\"") + button('action_respondida', 'Registrar respuesta', "invisible=\"state != 'enviada'\"") + field('state', 'widget="statusbar"') + '</header><sheet><h1>' + field('folio') + '</h1><group>' + fields('expediente_id company_id partner_id fecha_envio fecha_respuesta') + field('partida_ids', 'widget="many2many_tags"') + '</group></sheet><chatter/></form>')
    e += action('action_expedientes', 'Expedientes', 'licitacion.expediente')
    e += server_action('action_cartas_zip', 'Imprimir cartas de expedientes (ZIP)', 'expediente', 'action_print_cartas_zip')
    save('views/expediente_views.xml', e)

    c = view('view_carga_list', 'licitacion.carga', '<list create="0" decoration-warning="state == \'pendiente_asignacion\'">' + fields('fecha_snapshot archivo_nombre tipo_detectado subtipo_detectado tipo_archivo_id alcance registros state resumen user_id') + field('binary_sha256', 'optional="hide"') + field('reimportacion_forzada', 'optional="hide"') + field('procesado_el', 'optional="hide"') + '</list>')
    c += view('view_carga_form', 'licitacion.carga', '<form create="0" edit="0"><header>' + button('action_asignar', 'Asignar procedimiento', "invisible=\"state != 'pendiente_asignacion'\"") + button('action_preview', 'Previsualizar cambios', "invisible=\"state not in ('borrador','previsualizada')\"") + button('action_rechazar', 'Rechazar carga', "invisible=\"state in ('confirmada','rechazada')\"") + field('state', 'widget="statusbar"') + '</header><sheet>' + draft_banner() + '''<div class="alert alert-info" role="status" invisible="coincidencias_count &lt; 2">
Este binario tiene <field name="coincidencias_count" nolabel="1"/> cargas confirmadas. Se conserva el historial para auditoría.
<field name="coincidencias_ids" readonly="1"><list create="0" edit="0" delete="0"><field name="archivo_nombre"/><field name="fecha_snapshot"/><field name="procesado_el"/><field name="procesado_por_id"/><field name="resumen"/><field name="reimportacion_forzada"/><button name="action_open" string="Abrir" type="object"/></list></field></div>''' + '<group>' + fields('archivo_nombre fecha_snapshot tipo_detectado subtipo_detectado tipo_archivo_id procedimiento_id origen_portal alcance zona_horaria resumen nota_asignacion user_id procesado_el procesado_por_id carga_base_id binary_sha256') + field('company_ids', 'widget="many2many_tags"') + field('archivo', 'filename="archivo_nombre"') + '</group><group string="Reimportación" invisible="not reimportacion_forzada">' + fields('reimportacion_forzada motivo_reimportacion') + field('cargas_origen_ids', 'widget="many2many_tags"') + '</group><div class="alert alert-info" invisible="not aviso_base">' + field('aviso_base', 'nolabel="1"') + '</div></sheet><chatter/></form>')
    c += action('action_cargas', 'Historial de cargas', 'licitacion.carga')
    save('views/carga_views.xml', c)

    i = view('view_incidencia_list', 'licitacion.incidencia', '<list create="0" decoration-danger="severidad == \'bloqueante\' and state == \'abierta\'">' + fields('procedimiento_id identificador_observado origen campo valor_esperado valor_encontrado severidad state create_date') + '</list>')
    i += view('view_incidencia_form', 'licitacion.incidencia', '<form create="0" edit="0"><header>' + button('action_resolver', 'Resolver', "invisible=\"state != 'abierta'\" class=\"btn-primary\"") + button('action_ignorar', 'Ignorar', "invisible=\"state != 'abierta'\"") + field('state', 'widget="statusbar"') + '</header><sheet><group>' + fields('procedimiento_id identificador_observado partida_id carga_id origen campo severidad es_valor_no_reconocido detalle') + '</group><group><group string="Valor actual">' + field('valor_esperado', 'nolabel="1"') + '</group><group string="Valor encontrado">' + field('valor_encontrado', 'nolabel="1"') + '</group></group><group>' + fields('nota_resolucion resuelta_por_id fecha_resolucion escalada_fecha') + '</group></sheet><chatter/></form>')
    i += view('view_incidencia_search', 'licitacion.incidencia', '''<search><field name="procedimiento_id"/><field name="campo"/><filter name="abiertas" string="Abiertas" domain="[('state','=','abierta')]"/><filter name="bloqueantes" string="Bloqueantes" domain="[('severidad','=','bloqueante')]"/><group><filter name="por_origen" string="Origen" context="{'group_by':'origen'}"/><filter name="por_procedimiento" string="Procedimiento" context="{'group_by':'procedimiento_id'}"/></group></search>''')
    i += action('action_incidencias', 'Incidencias', 'licitacion.incidencia', extra='<field name="context">{\'search_default_abiertas\':1}</field>')
    save('views/incidencia_views.xml', i)

    a = view('view_agenda_calendar', 'licitacion.fecha.fatal', '<calendar string="Agenda de fechas fatales" date_start="fecha" color="tipo" mode="month" create="0" edit="0" delete="0" event_open_popup="true">' + fields('name tipo user_id') + '</calendar>')
    a += view('view_agenda_list', 'licitacion.fecha.fatal', '<list create="0" edit="0" delete="0" decoration-danger="fecha &lt; now and state == \'detectado\'">' + fields('fecha tipo procedimiento_id state user_id') + button('action_open_procedimiento', 'Abrir') + '</list>')
    a += view('view_agenda_form', 'licitacion.fecha.fatal', '<form create="0" edit="0" delete="0"><header>' + button('action_open_procedimiento', 'Abrir procedimiento') + '</header><sheet><group>' + fields('procedimiento_id tipo fecha user_id') + '</group></sheet></form>')
    a += view('view_agenda_search', 'licitacion.fecha.fatal', '''<search><field name="procedimiento_id"/><filter name="proximas" string="Próximas 72 h" domain="[('fecha','&gt;=',datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')),('fecha','&lt;=',(datetime.datetime.now()+relativedelta(hours=72)).strftime('%Y-%m-%d %H:%M:%S')),('state','not in',['descartado','no_viable','con_fallo'])]"/><filter name="vencidas" string="Vencidas sin actuar" domain="[('fecha','&lt;',datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')),('state','=','detectado')]"/><filter name="juntas" string="Juntas" domain="[('tipo','=','junta')]"/><filter name="preguntas" string="Preguntas" domain="[('tipo','=','preguntas')]"/><group><filter name="tipo" string="Tipo de evento" context="{'group_by':'tipo'}"/><filter name="responsable" string="Responsable" context="{'group_by':'user_id'}"/></group></search>''')
    a += action('action_agenda', 'Agenda', 'licitacion.fecha.fatal', 'calendar,list,form')
    save('views/agenda_views.xml', a)

    catalogs = [('unidad.compradora', 'Unidades compradoras', 'dependencia entidad_id'), ('estatus.portal', 'Estatus portal', 'tipo estado'), ('motivo.descarte', 'Motivos de descarte', 'aplica_a'), ('tipo.contratacion', 'Tipos de contratación', 'clave_identificador'), ('entidad.federativa', 'Entidades federativas', ''), ('clave.cucop', 'Claves CUCoP+', '')]
    c = ''
    for model, label, extras in catalogs:
        slug = model.replace('.', '_')
        if model == 'entidad.federativa':
            content = fields('codigo_in nombre nombres_alternativos activa notas procedimiento_count')
            c += view('view_' + slug + '_list', 'licitacion.' + model, '<list create="0" delete="0">' + content + '</list>')
            c += view('view_' + slug + '_form', 'licitacion.' + model, '<form create="0" delete="0"><sheet><group>' + content + '</group></sheet></form>')
            c += action('action_' + slug, label, 'licitacion.' + model)
            continue
        c += view('view_' + slug + '_list', 'licitacion.' + model, '<list>' + fields('code name ' + extras + ' active') + '</list>')
        chatter = '<chatter/>' if model == 'estatus.portal' else ''
        c += view('view_' + slug + '_form', 'licitacion.' + model, '<form><sheet><group>' + fields('code name ' + extras + ' active') + '</group></sheet>' + chatter + '</form>')
        c += action('action_' + slug, label, 'licitacion.' + model)
    c += '''<record id="view_partner_licitacion" model="ir.ui.view"><field name="name">res.partner.licitacion</field><field name="model">res.partner</field><field name="inherit_id" ref="base.view_partner_form"/><field name="arch" type="xml"><xpath expr="//notebook" position="inside"><page string="Licitaciones" groups="licitaciones_publicas.group_licitaciones_user"><group><field name="es_proveedor_licitacion"/><field name="claves_cucop_ids" widget="many2many_tags"/><field name="actividad_licitacion"/></group></page></xpath></field></record>'''
    c += action('action_proveedores', 'Proveedores de licitaciones', 'res.partner', extra='<field name="domain">[(\'es_proveedor_licitacion\',\'=\',True)]</field><field name="context">{\'default_es_proveedor_licitacion\':True}</field>')
    save('views/catalog_views.xml', c)
    save('views/settings_views.xml', '''<record id="view_licitaciones_settings" model="ir.ui.view"><field name="name">licitaciones.settings</field><field name="model">res.config.settings</field><field name="inherit_id" ref="base.res_config_settings_view_form"/><field name="arch" type="xml"><xpath expr="//form" position="inside"><app string="Licitaciones" name="licitaciones_publicas" groups="licitaciones_publicas.group_licitaciones_manager"><block title="Seguimiento"><setting string="Escalamiento de incidencias"><field name="licitaciones_escalamiento_horas"/></setting><setting string="Ubicación documental prevista" help="Referencia para una futura migración. Los archivos actuales permanecen en el filestore de Odoo."><field name="licitaciones_storage_destino"/></setting></block></app></xpath></field></record>
<record id="view_company_licitaciones" model="ir.ui.view"><field name="name">company.licitaciones</field><field name="model">res.company</field><field name="inherit_id" ref="base.view_company_form"/><field name="arch" type="xml"><xpath expr="//notebook" position="inside"><page string="Licitaciones" groups="licitaciones_publicas.group_licitaciones_manager"><group><field name="representante_legal"/><field name="firma_representante_legal" widget="image"/></group></page></xpath></field></record>
<record id="action_licitaciones_settings" model="ir.actions.act_window"><field name="name">Ajustes de licitaciones</field><field name="res_model">res.config.settings</field><field name="view_mode">form</field><field name="target">current</field><field name="context">{'module':'licitaciones_publicas'}</field></record>''')
    menus = '<menuitem id="menu_root" name="Licitaciones" sequence="30" groups="group_licitaciones_user" web_icon="licitaciones_publicas,static/description/icon.svg"/>'
    for xmlid, name, target, seq in [('agenda', 'Agenda', 'action_agenda', 1), ('procedimientos', 'Procedimientos', 'action_procedimientos', 3), ('partidas', 'Renglones', 'action_partidas', 4), ('expedientes', 'Expedientes', 'action_expedientes', 5), ('incidencias', 'Incidencias', 'action_incidencias', 6)]:
        menus += f'<menuitem id="menu_{xmlid}" name="{name}" parent="menu_root" action="{target}" sequence="{seq}"/>'
    menus += '<menuitem id="menu_cargas" name="Cargas" parent="menu_root" sequence="2"/><menuitem id="menu_carga_nueva" name="Nueva carga" parent="menu_cargas" action="action_carga_wizard" sequence="1"/><menuitem id="menu_carga_historial" name="Historial" parent="menu_cargas" action="action_cargas" sequence="2"/><menuitem id="menu_config" name="Configuración" parent="menu_root" sequence="90"/>'
    for n, (model, label, _) in enumerate(catalogs, 1):
        slug = model.replace('.', '_')
        menus += f'<menuitem id="menu_{slug}" name="{label}" parent="menu_config" action="action_{slug}" sequence="{n}"/>'
    menus += '<menuitem id="menu_proveedores" name="Proveedores" parent="menu_config" action="action_proveedores" sequence="8"/><menuitem id="menu_settings" name="Ajustes" parent="menu_config" action="action_licitaciones_settings" groups="base.group_system" sequence="90"/>'
    save('views/menus.xml', menus)


def server_action(xmlid, label, model, method):
    return f'<record id="{xmlid}" model="ir.actions.server"><field name="name">{label}</field><field name="model_id" ref="model_licitacion_{model}"/><field name="binding_model_id" ref="model_licitacion_{model}"/><field name="state">code</field><field name="code">action = records.{method}()</field></record>'


if __name__ == '__main__':
    generate()
