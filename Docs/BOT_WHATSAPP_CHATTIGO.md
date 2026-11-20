# Bot de WhatsApp por Chattigo

> **Desde 2026-11-19 el canal es Meta directo** (WhatsApp Cloud API): la licencia
> de Chattigo con Meta es ISV y el número se atiende sin intermediario. Ver
> «Meta directo» al final. Lo de Chattigo queda como alternativa.

El bot vive en `apps/consulta` y sólo consulta la proyección de descargas de la
DMZ. No abre conectividad hacia Oracle ni hacia la base operativa. El webhook
solamente inserta en una cola durable; el worker usa otro rol para leer la cola,
consultar descargas y enviar la respuesta.

## Estado del despliegue

En el VPS de Suite-Turnos/Juviar están aplicadas las migraciones del bot. Los
roles `consulta_webhook` y `consulta_bot` tienen contraseñas aleatorias guardadas
en `/etc/suite/bot.env`. La unidad `bot-whatsapp.service` está instalada,
**deshabilitada e inactiva** hasta completar los datos externos.

No registrar el webhook en Chattigo hasta superar la prueba previa completa. Al
registrarlo, el número deja de entregar los mensajes al bot anterior.

## Datos externos pendientes

- URL base, usuario, clave y DID de Chattigo.
- Confirmación y revisión manual de los contactos que no pudieron vincularse
  de forma exacta y única con un `CLIENTECUIT`.
- Dominio HTTPS: `juviar-bot.duckdns.org`, apuntado al VPS mediante DuckDNS.
- Si Chattigo las provee, IP de salida para filtrarlas además en nginx.

## Importación de teléfonos

La identidad del productor es `CLIENTECUIT`. `NROINSCRIPTO` identifica a la
bodega y no debe usarse para autorizar consultas individuales. El CSV de carga
tiene exclusivamente los encabezados `telefono,clientecuit`.

Después de revisar el CSV privado:

```bash
set -a
. /etc/suite/recepcion.env
. /etc/suite/bot.env
set +a
PYTHONPATH=apps/api/src python -m \
  suite_juviar.plataforma.terceros.infrastructure.importar_whatsapp \
  /ruta/vinculos.csv --por "responsable"
```

La salida separa inválidos y teléfonos que no comienzan con `549`; esos casos
deben revisarse antes del cambio de canal.

El archivo fuente y el CSV de importación permanecen fuera de Git, con permisos
`600`. Una vez confirmada la importación, la publicación en DMZ y la prueba de
consulta, se eliminan. La lista de revisión se conserva privada sólo mientras
sea necesaria para resolver excepciones.

## Puesta en marcha segura

1. Completar las variables `CHATTIGO_*` de `/etc/suite/bot.env`.
2. La app Consulta se ejecuta como `consulta-publica.service`; Caddy publica
   exclusivamente `/webhook/chattigo/*` en `https://juviar-bot.duckdns.org`.
3. Simular el webhook con un teléfono de prueba registrado. Confirmar respuesta
   real en menos de 10 segundos.
4. Confirmar 404 sin secreto y con secreto incorrecto.
5. Enviar dos veces el mismo `wamid`; debe quedar una fila y una respuesta.
6. Habilitar el worker: `systemctl enable --now bot-whatsapp.service`.
7. Coordinado con Juviar-ENAV, registrar el webhook una sola vez:

```bash
set -a
. /etc/suite/bot.env
set +a
PYTHONPATH=apps/consulta/src python -m consulta_publica.bot.configurar_webhook \
  https://juviar-bot.duckdns.org/webhook/chattigo
```

Para volver atrás, Juviar-ENAV debe registrar nuevamente la URL anterior en
Chattigo. Durante la primera semana revisar diariamente mensajes en estado
`error`; ese período forma parte del criterio de cierre.

## Simulador interno

Mientras faltan las credenciales de Chattigo, el worker usa
`BOT_TRANSPORTE=simulado`. El simulador escucha exclusivamente en loopback del
VPS y no está publicado por Caddy. Para usarlo:

```bash
ssh -N -L 8099:127.0.0.1:8099 root@173.212.195.122
```

Después abrir `http://127.0.0.1:8099`. El simulador sólo puede usar vínculos
`telefono → CLIENTECUIT`; no se permiten vínculos por `NROINSCRIPTO`.

Antes de activar Chattigo es obligatorio eliminar los vínculos ficticios:

```bash
set -a
. /etc/suite/terceros.env
set +a
PYTHONPATH=/opt/suite-juviar:/opt/suite-juviar/apps/api/src \
  /opt/suite-juviar/.venv/bin/python -m apps.simulador.cargar_vinculos_prueba --borrar
```

Luego cambiar a `BOT_TRANSPORTE=chattigo`, quitar `BOT_FECHA_SIMULADA`, detener
`bot-simulador.service` y recién entonces registrar el webhook en Chattigo.


## Meta directo (WhatsApp Cloud API)

Dirección que se carga en la app de Meta (WhatsApp → Configuración → Webhook):

- **URL de devolución de llamada:** `https://juviar-bot.duckdns.org/webhook/meta`
- **Token de verificación:** el valor de `META_TOKEN_VERIFICACION`.
- **Campo suscripto:** `messages`.

Meta primero hace un `GET` con `hub.mode=subscribe`, `hub.verify_token` y
`hub.challenge`; si el token coincide se devuelve el challenge. Después cada aviso
llega por `POST` firmado con la clave secreta de la app (`X-Hub-Signature-256`);
sin firma válida se responde 403 y no se encola nada. Si `META_CLAVE_APP` o
`META_TOKEN_VERIFICACION` faltan, la dirección responde 404.

Variables en `/etc/suite/bot.env` (nunca en Git ni por chat):

| Variable | Dónde está en Meta |
|---|---|
| `META_TOKEN` | Token permanente de un usuario del sistema (Administrador comercial → Usuarios del sistema), con `whatsapp_business_messaging` y `whatsapp_business_management` |
| `META_NUMERO_ID` | WhatsApp → Configuración de la API → «Identificador del número de teléfono» |
| `META_CUENTA_ID` | Mismo lugar → «Identificador de la cuenta de WhatsApp Business» |
| `META_CLAVE_APP` | Configuración de la app → Básica → «Clave secreta de la app» |
| `META_TOKEN_VERIFICACION` | Lo generamos nosotros (48 caracteres al azar) y se pega en Meta |

Caddy publica `/webhook/meta` hacia `172.18.0.1:8021`, igual que el de Chattigo.

Puesta en marcha:

1. Cargar las variables y `BOT_TRANSPORTE=meta`; quitar `BOT_FECHA_SIMULADA`.
2. Reiniciar `consulta-publica` y `bot-whatsapp`.
3. En Meta, cargar URL y token de verificación y suscribir `messages`.
4. Suscribir la cuenta a la app:
   `PYTHONPATH=apps/consulta/src python -m consulta_publica.bot.configurar_webhook x`
   (con `BOT_TRANSPORTE=meta` sólo suscribe la cuenta).
5. Escribir al número desde un teléfono registrado y confirmar la respuesta.

Los mensajes que el bot manda sin que la persona haya escrito en las últimas 24 h
(avisos de turnos, mosto) Meta sólo los acepta como **plantillas aprobadas**;
mientras no estén, esos avisos quedan con error y se ven en Gestión.
