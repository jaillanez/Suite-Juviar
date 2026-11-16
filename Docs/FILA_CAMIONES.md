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

## Ofertas de uva de la temporada (infra/038)

El bot ya no reserva días. En "Ofrecer uva" el productor elige la bodega y dice
cuántos kilos ofrece de cada variedad para toda la temporada. La oferta queda
pendiente en Gestión → Turnos de cosecha → Ofertas de la temporada, donde la
bodega:

- compara lo ofrecido con lo entregado en los últimos años (parámetro, 3 por
  defecto) y ve la alerta cuando el total supera el promedio más el margen;
- filtra por productores constantes, sólo del último año o sin entregas;
- asigna los días corridos sin domingos con los kilos por día de ese productor
  (quedan guardados para la próxima vez). Pasarse de la capacidad del día se
  avisa pero no bloquea;
- detiene una oferta por falta de grado (semanas configurables) o la desestima;
- carga ofertas de productores nuevos con CUIT y nombre (alta preliminar).

Al asignar se crean los turnos de cada día en `fila.turno` (los que ven el
guardia y Báscula) y se encola un aviso en `fila.aviso_productor`; el worker del
bot lo envía. Con Chattigo real, un aviso fuera de la ventana de 24 h necesita
plantilla aprobada.

Aplicar `infra/038_ofertas_uva.sql` en la DMZ antes de desplegar el bot y Gestión.
