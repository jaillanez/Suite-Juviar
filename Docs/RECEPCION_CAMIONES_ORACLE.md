# Recepción de camiones de Juviar-ENAV desde Oracle

Este bloque sincroniza `V_DETALLE_MOVIMIENTOS` desde Oracle hacia la base interna de
Suite Juviar y publica una proyección mínima en la base DMZ. No reemplaza el dominio de
romaneos propio: es un adaptador de integración con el sistema existente.

## Estado de habilitación

La IP fija de salida autorizada para Juviar-ENAV es `173.212.195.122`. La conectividad
TCP a Chimbas (`200.114.96.131:1521`) fue verificada correctamente el 21 de septiembre
de 2026. No se debe ejecutar la carga inicial hasta que el diagnóstico real termine con
`RESULTADO: ok`.

## Configuración

1. Instalar API y Consulta en el entorno virtual:

   ```bash
   uv pip install --python .venv/bin/python -e "apps/api[dev]" -e apps/consulta
   ```

2. Copiar `infra/recepcion.env.example` a `/etc/suite/recepcion.env`, reemplazar todos
   los marcadores y restringirlo a modo `600`. Los DSN administrativos se usan sólo
   para migrar; no deben quedar en el servicio.

3. Exportar las variables del archivo antes del diagnóstico. Desde `apps/api`, ejecutar:

   ```bash
   python -m suite_juviar.modulos.recepcion.integracion_oracle.diagnostico chimbas
   ```

   Faltantes de columnas, CIU nulo o CIU repetido son bloqueantes. En ese caso no se
   aplican migraciones ni se ejecuta el worker.

## Migración y primera carga

Con el diagnóstico aprobado:

```bash
psql "$DSN_SUITE_ADMIN" -f infra/009_recepcion_oracle.sql
psql "$DSN_DMZ_ADMIN" -f infra/010_consulta_descargas.sql
cd apps/api
python -m suite_juviar.modulos.recepcion.integracion_oracle.worker inicial
```

La clave, verificada sobre las 18.595 filas de la vista, es `(sede, ciu, id_origen)`.
Las correcciones conservan la versión anterior en
`recepcion.descarga_cambio`; una ausencia nunca borra la fila. Una publicación fallida
permanece con `pendiente_publicar = true` y se reintenta en la corrida siguiente.

Los registros históricos con `FECHA` nula se importan como `incompleto_en_origen`, no
como camiones en descarga. Sólo una fila nueva sin fecha detectada por la ventana
operativa se publica como `en_descarga`.

## Servicios

Copiar los cuatro archivos de `infra/systemd/` a `/etc/systemd/system/` y luego:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now recepcion-ventana.timer recepcion-nocturna.timer
systemctl list-timers 'recepcion-*'
```

El servicio corto relee 15 días cada cinco minutos. El nocturno relee 200 días a las
03:00. Los dos usan un advisory lock por sede para impedir solapamientos.

## API de Consulta

El proceso `consulta_publica.main:app` exige al arrancar:

- `CONSULTA_API_KEY_JUVIAR`: al menos 32 caracteres;
- `CONSULTA_DSN_LECTOR`: DSN del rol `consulta_lector` en la DMZ.

Los endpoints `/v1/productores/{nroinscripto}/ultima`, `/resumen` y `/descargas` exigen
`X-Api-Key`, filtran por número de inscripto, registran auditoría y devuelven `datos_al`.
La proyección no contiene CUIT, chofer ni cliente.

## Verificación

```bash
PYTHONPATH=apps/api/src:apps/consulta/src \
  .venv/bin/pytest -c apps/api/pyproject.toml apps/api/tests/recepcion_oracle -q
```

El cierre productivo exige además una semana de corridas observadas y comprobar con los
roles reales que `consulta_lector` no puede ejecutar `UPDATE` ni `DELETE`.
