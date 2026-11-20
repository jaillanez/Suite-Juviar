# RRHH por WhatsApp (fase 5)

Lo que pidió la empresa en la reunión: CV por WhatsApp, certificados médicos y pedidos de EPP del
personal, y el aviso de llegada del micro de personal.

## CV por WhatsApp

Un número que **no** es productor ni está en «Personal en el bot» manda un PDF o una foto (JPG, PNG o
WEBP, hasta 5 MB): el bot lo toma como CV y contesta que lo recibió. Gestión lo incorpora a
Selección por el mismo camino que los CV del mail de RRHH (mismo guardado, misma extracción), con
origen `WHATSAPP` y el teléfono como dato de contacto (sin verificar). Un número desconocido que sólo
manda texto sigue recibiendo «no registrado», con una línea más: que para postularse mande el CV.

## Certificados médicos y pedidos de EPP

El personal cargado en «Personal en el bot» manda:

- **Certificado médico**: foto o PDF con una palabra como «certificado», «médico», «reposo» o «licencia».
- **Pedido de EPP**: texto (y si quiere una foto) con «EPP», «guantes», «botines», «casco», «ropa»…
- **Mantenimiento**: igual que antes («salida», «taller», «remito»…; ver `REMITOS_MANTENIMIENTO.md`).

Una foto o un PDF **sin** palabra reconocida ya no va a Mantenimiento: el bot pide que lo mande de
nuevo diciendo para qué es. El saludo al personal lista las tres cosas.

Todo queda **pendiente de revisión** en Gestión → RRHH → «WhatsApp del personal» (perfil RRHH). Ahí
se ve empleado (legajo, nombre y empresa salen del teléfono), tipo, texto, archivo y fecha:

- Certificado: Gestión lo lee con el mismo lector de Salud (`analizar_certificado`; la IA externa sólo
  si está permitida igual que en Salud) y deja días, fechas y profesional **precargados** para que
  RRHH los confirme o corrija. «Pasar al legajo» guarda el archivo como adjunto del legajo del
  empleado **y lo carga en Salud** (ver abajo).
- Pedido de EPP: «Marcar atendido» con una nota (en EPP no hay un pedido de entrega al que enlazarlo).
- Cualquiera: «Descartar» con motivo. Todo deja quién y cuándo.

**El certificado en Salud.** El diagnóstico es secreto médico: RRHH nunca lo ve (ni en la bandeja ni
en las respuestas de la API). Lo que leyó el lector de diagnóstico y resumen se guarda aparte, cifrado
con el resto de la bandeja, y sólo lo ve el perfil médico.

- Al pasar al legajo, si se leyó un diagnóstico que está en el catálogo de Salud y hay fechas, días y
  profesional (los que confirmó RRHH; sin días, salen de las fechas), el certificado se carga solo en
  Salud con el mismo archivo. En la bandeja RRHH ve «En legajo y en Salud».
- Si falta el diagnóstico (o no es del catálogo, o falta un dato, o Salud no responde), queda «En
  legajo, pendiente de Salud». El servicio médico lo ve en Salud → «Por WhatsApp» (permisos
  `salud.diagnostico.leer` y `salud.certificado.gestionar`): el archivo, los datos que confirmó RRHH,
  el diagnóstico leído si hubo y por qué quedó pendiente. Elige el diagnóstico del catálogo (puede
  corregir fechas, días o profesional) y lo carga.
- Queda en la bitácora de Salud: la carga automática (con el usuario de RRHH que la disparó), la
  consulta de los pendientes, cada vez que se abre el archivo y la carga del médico.

**Confirmación del empleado**: después de leer el certificado, el bot le manda al empleado los días y
las fechas leídos y le pregunta «1 = Sí, es correcto / 2 = No». Si contesta 2, le pide que escriba lo
correcto y eso queda como corrección. La respuesta se ve en la bandeja; el certificado sigue pendiente
de RRHH. Si no se pudo leer nada, no se pregunta: el bot le avisa que lo revisa RRHH. La espera vence
a las 24 horas (después queda «sin confirmar» y una respuesta vieja no se engancha).

## Aviso del micro de personal

En Gestión → «WhatsApp del personal» → «Recorridos del micro», RRHH carga los **recorridos** (bodega,
nombre, activo) y en «Personal y su recorrido» le asigna a cada empleado el suyo (permiso
`rrhh.micro.gestionar`). RRHH sólo cambia el recorrido: el alta, la baja y el tipo del personal
siguen en «Personal en el bot» (Superadministrador), que también puede asignarlo. La guardia, en su consola, toca **«Llegó el micro»** y elige el
recorrido: el bot avisa por WhatsApp al personal activo de ese recorrido. No se acepta otro aviso del
mismo recorrido dentro de 5 minutos (doble toque). Un aviso que no salió en 30 minutos ya no se manda.

El texto del aviso está en un solo lugar (`texto_aviso_micro` en `apps/consulta/.../bot/worker.py`).
Meta sólo entrega los mensajes que inicia la empresa fuera de la ventana de 24 horas si son
**plantillas aprobadas**: para que el aviso llegue a quien no escribió en el día hay que aprobar una
plantilla y mandarla desde ahí. Todavía no está hecho.

## Base de la fila (`infra/042_rrhh_whatsapp.sql`)

| Qué | Tablas | Funciones (rol) |
|---|---|---|
| Recorridos | `fila.recorrido_micro`, `consulta.telefono_personal.recorrido_id` | `guardar_recorrido_micro`, `consulta.asignar_recorrido_personal` (gestion_tablero); `recorridos_micro` (fila_guardia) |
| Mensajes para RRHH | `fila.mensaje_rrhh` | `recibir_mensaje_rrhh` (consulta_bot); `mensajes_rrhh_pendientes`, `confirmar_mensajes_rrhh` (gestion_tablero) |
| Confirmación | columnas de `fila.mensaje_rrhh` | `avisar_lectura_certificado`, `confirmaciones_certificados` (gestion_tablero); `confirmacion_certificado_pendiente`, `responder_certificado` (consulta_bot) |
| CV | `fila.cv_whatsapp` | `recibir_cv_whatsapp` (consulta_bot); `cvs_whatsapp_pendientes`, `confirmar_cvs_whatsapp` (gestion_tablero) |
| Aviso del micro | `fila.aviso_micro` | `avisar_llegada_micro` (fila_guardia) |
| Cola al personal | `fila.aviso_personal` | `tomar_avisos_personal`, `marcar_aviso_personal` (consulta_bot) |
| Webhook | `consulta.bot_entrada.media_nombre`, `media_tipo` | `consulta.encolar_bot_archivo` (consulta_webhook) |

Tipos y tamaños se controlan en el bot (por los primeros bytes del archivo) y en la base. Los
archivos se borran de la DMZ apenas Gestión confirma que los guardó; en Gestión la bandeja se guarda
cifrada (AES-GCM, la misma clave que los adjuntos del legajo). Gestión sincroniza cada minuto y al
abrir la bandeja (`SJ_SINCRONIZAR_RRHH_WHATSAPP=0` lo apaga).

## Instalación

Aplicar `infra/042_rrhh_whatsapp.sql` en la base de la fila **antes** de instalar el código del bot,
de la guardia y de Gestión (el bot ya lee las columnas nuevas de la cola). Es idempotente.
