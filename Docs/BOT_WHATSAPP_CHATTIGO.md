# Bot de WhatsApp por Chattigo

El bot vive en `apps/consulta` y sólo consulta la proyección de descargas de la
DMZ. No abre conectividad hacia Oracle ni hacia la base operativa. El webhook
solamente inserta en una cola durable; el worker usa otro rol para leer la cola,
consultar descargas y enviar la respuesta.

## Estado del despliegue

En el VPS de Suite-Turnos/Juviar están aplicadas las migraciones 011 y 012. Los
roles `consulta_webhook` y `consulta_bot` tienen contraseñas aleatorias guardadas
en `/etc/suite/bot.env`. La unidad `bot-whatsapp.service` está instalada,
**deshabilitada e inactiva** hasta completar los datos externos.

No registrar el webhook en Chattigo hasta superar la prueba previa completa. Al
registrarlo, el número deja de entregar los mensajes al bot anterior.

## Datos externos pendientes

- URL base, usuario, clave y DID de Chattigo.
- CSV `telefono,nroinscripto` de Juviar-ENAV.
- Dominio HTTPS: `juviar-bot.duckdns.org`, apuntado al VPS mediante DuckDNS.
- Si Chattigo las provee, IP de salida para filtrarlas además en nginx.

## Importación de teléfonos

Después de recibir y revisar el CSV:

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
