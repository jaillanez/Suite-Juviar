# Fila de camiones y turnos

El servicio `apps/fila` vive separado del backend interno. Usa exclusivamente
la base DMZ y cuatro roles distintos: público, guardia, turnos y worker.

## Rutas

- `/r/<sede>`: alta del chofer mediante el QR del portón.
- `/t/<ticket>`: estado de un solo viaje mediante un token aleatorio.
- `/guardia/<sede>`: tablet del guardia, con cola offline en IndexedDB.
- `/pantalla/<sede>#<token>`: pantalla de espera sin nombres de productores.
- `/turnos`: entrada móvil desde el enlace temporal de WhatsApp.

La tablet es una PWA liviana. Cada acción lleva un UUID de cliente; los
reintentos posteriores a un corte de señal son idempotentes. El servidor no
acepta horas de tablet futuras ni con más de doce horas de antigüedad.

## Migraciones

Se aplican en este orden:

1. `infra/018_permisos_contactos.sql` en Suite.
2. `infra/019_permisos_contactos_dmz.sql` en DMZ.
3. `infra/020_fila_camiones.sql` en DMZ.

Antes de iniciar el servicio se crean contraseñas aleatorias para los cuatro
roles y `/etc/suite/fila.env` con propietario `suite`, modo `600`. No se guardan
tokens, contraseñas ni la pimienta de invitaciones en Git.

## Límites deliberados

El bot y los avisos proactivos continúan apagados hasta obtener credenciales y
plantilla de Chattigo. Lavalle y Media Agua no se habilitan hasta que sus vistas
Oracle existan y autoricen la IP del VPS. La capacidad y los certificados
orgánicos deben cargarlos la bodega antes de ofrecer turnos.
