# Actualizar la suite en el servidor

En el servidor corren desde Git: la consulta pública y el bot (puerto 8021), la fila de
camiones (8022 y su proceso de cierre), el publicador de contactos y las sincronizaciones de
recepción (temporizadores `recepcion-ventana` y `recepcion-nocturna`).

## Cómo está armado

- `/opt/suite-juviar`: copia de Git y entorno de Python (`.venv`). No se edita a mano.
- `/opt/suite-juviar-releases/<commit>`: cada versión instalada, copiada tal cual de Git.
- `/opt/suite-juviar-releases/actual`: la versión que usan los servicios.
- `/opt/suite-juviar-releases/anterior`: la versión que estaba antes, para volver atrás.

Cada servicio tiene un `release.conf` en `/etc/systemd/system/<servicio>.service.d/`
que lo apunta a `actual`. Las claves siguen en `/etc/suite/*.env`, fuera de Git.

## Actualizar

Como root en el servidor:

```bash
bash /opt/suite-juviar/infra/desplegar.sh
```

Instala lo último de `main`. El script:

1. se niega si alguien editó archivos a mano en `/opt/suite-juviar`;
2. copia la versión a su carpeta e instala las dependencias de Python que falten;
3. prueba que cada servicio cargue con la versión nueva, sin tocar lo que está en marcha;
4. cambia `actual`, reinicia los servicios y comprueba que respondan;
5. si algo falla, vuelve solo a la versión anterior.

Para instalar una versión puntual: `bash /opt/suite-juviar/infra/desplegar.sh <commit>`.

## Volver atrás

```bash
bash /opt/suite-juviar/infra/desplegar.sh --volver
```

Los cambios de base de datos (`infra/*.sql`) no los aplica el script: se aplican a mano y
antes de actualizar, como indica cada archivo.
