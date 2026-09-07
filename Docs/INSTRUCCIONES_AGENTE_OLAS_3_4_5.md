# Instrucciones para el agente — Olas 3, 4 y 5

**Continúa:** `INSTRUCCIONES_AGENTE.md`.
**Rama:** `codex/rrhh-epp-unificado`. Sigue sin fusionar a `main`.

Cambia el criterio anterior. Las olas 3, 4 y 5 se construyen **ahora**, completas,
con adaptadores simulados. La regla que rige todo este documento:

> **El límite no es el módulo, es el adaptador.** Se construye la lógica entera.
> Lo único que espera es la conexión con lo de afuera. Y nunca se muestra un
> número fabricado como si fuera una conclusión real.

---

## Paso 0 — Los documentos, primero

El informe de estado dice que la Base Común v0.4, el README del módulo y el plan
no están en el repositorio, y que por eso no se pudo actualizar §6.2. Antes de
escribir una línea de estos tres módulos:

- Copiar a `Docs/` la Base Común v0.4, `PLAN_DE_IMPLEMENTACION.md`,
  `INSTRUCCIONES_AGENTE.md` y este documento.
- Actualizar §6.2 de la Base Común con el orden real: EPP → Selección →
  Capacitaciones → resto. Dejar escrito por qué Turnos bajó de la etapa 1: está
  bloqueado por el diccionario de Time, no por prioridad.

---

## Las tres marcas obligatorias

Valen para los tres módulos, sin excepción. Es lo que permite construir sin
mentir:

1. **Franja roja en pantalla** mientras la fuente de ese módulo sea simulada.
2. **Marca en el documento y en toda exportación.** Un PDF, un Excel o una
   pantalla impresa salen con "datos simulados — sin validez". Si alguien
   fotografía la pantalla en una reunión, la marca tiene que salir en la foto.
3. **Negativa a arrancar** con `ENTORNO=produccion` si la fuente del módulo sigue
   siendo simulada. El mismo mecanismo que ya tiene EPP con Nexus.

Cada una lleva su prueba negativa (§6.5): configuración mal puesta a propósito,
que confirme que la aplicación efectivamente se niega.

---

## Paso 1 — Reclamo de calidad en la entrega

**Va primero, antes que la analítica, aunque parezca parte de la Ola 3.** Es
captura de dato: cada día que pasa sin esto es un dato que después no se
reconstruye.

En la pantalla de entrega del depósito, cuando alguien devuelve algo roto o
gastado antes de tiempo:

- Motivo, elegido de una lista corta (rotura, desgaste prematuro, talle, molestia
  de uso, defecto de fábrica). Sin texto libre.
- Queda ligado al **ítem** —marca y modelo—, no al elemento normativo.
- Es opcional: no puede frenar una entrega. Si el operario no lo carga, la
  entrega se registra igual.

Esto se hace sobre los datos reales apenas el sistema entre en uso, sin esperar
nada de la empresa.

---

## Ola 3 — Analítica de EPP para Compras

Ruta: `modulos/epp_analitica`. **De sólo lectura.** No tiene tablas propias: lee
del repositorio de entregas de `rrhh_epp` a través de un puerto. No duplicar
datos ni armar un almacén paralelo.

### Qué calcula

- Duración real por ítem, cruzada por puesto y por sector.
- Consumo por período.
- Reclamos de calidad por ítem y por motivo.
- Comparación entre dos ítems del mismo elemento normativo.
- Costo por persona y por período (ver el punto del precio, abajo).

### El precio no existe todavía

Hoy el sistema no conoce el precio de nada. Definir el puerto `PrecioItem` con
adaptador simulado, **dueño del dato: Compras**. Mientras no haya precios reales,
las métricas de costo se muestran vacías con la leyenda de qué falta — no en
cero, que se lee como si costara cero.

### Muestra insuficiente

Regla dura: **nunca mostrar un promedio de duración calculado sobre menos de N
entregas.** Definir N, dejarlo configurable, y mostrar "sin datos suficientes" en
lugar del número. Una duración promedio sacada de dos entregas es exactamente el
tipo de dato que después hace perder una discusión con Compras.

### Marca de simulación

Además de las tres marcas generales: mientras haya entregas registradas contra
ítems `SIM-*`, toda comparación de proveedores sale marcada y **no se puede
exportar** como evidencia. Cuando llegue el catálogo real de HyS, el reemplazo es
un reemplazo, no una fusión: los `SIM-*` se dan de baja y las entregas que los
referencian quedan marcadas como de período de prueba.

**Terminado cuando** la pantalla que va a ver Compras existe, es navegable y se
puede mostrar en una reunión sin que nadie confunda la muestra con un informe.

---

## Ola 4 — Legajo digital y salud

Dos módulos, no uno: `modulos/legajo` y `modulos/salud`. La separación es del día
uno; después no se separa.

### `modulos/legajo`

- Ficha por persona sobre el puerto de legajos que ya existe (adaptador simulado
  de `rrhh_epp`, sin duplicarlo).
- Adjuntos escaneados, cifrados como los CV, con el original intacto.
- ENAV y Jubiar usan formatos de ficha distintos: se guardan los mismos datos y
  se emite el formato que corresponde a la empresa del legajo.

### `modulos/salud`

- Certificado médico con **diagnóstico**, elegido de un catálogo, no escrito a
  mano. Definir el puerto `CatalogoDiagnostico` con una lista de muestra
  marcada; **dueño del dato: el servicio médico**, que es quien tiene que
  decidir si usan CIE-10 o una lista propia.
- Rol propio. Un usuario con perfil de RRHH general **no ve el diagnóstico**.
- **Bitácora de consulta:** queda registrado quién lo miró, no sólo quién lo
  cargó. Es lo que diferencia un dato sensible bien tratado de uno mal tratado.
- Reportes de estacionalidad y por enfermedad: siempre agregados, nunca
  nominados.

### El aviso del artículo 208

La lógica se construye ahora. El cómputo depende de antigüedad y cargas de
familia, que salen de Nexus, así que con la fuente simulada el aviso sale
marcado como **preliminar**. Cuando se enchufe Nexus real, la marca se cae sola.

### Pruebas negativas obligatorias

1. Un usuario con rol de RRHH general intenta leer un diagnóstico: rechazado.
2. Control negativo: el permiso mal configurado a propósito, para confirmar que
   la prueba falla cuando tiene que fallar.
3. Un reporte nominado que intente incluir el diagnóstico: rechazado.
4. Consulta sin rol y consulta con rol nulo, las dos.

---

## Ola 5 — Conciliación de turnos

Ruta: `modulos/turnos`. Acá está el único límite real, y está en un solo lugar:
**el adaptador de Time.**

### Se construye ahora, con modelo propio

El modelo de turno, cronograma, fichada, desvío e imputación es **lógica propia**
y no depende de cómo Time guarde nada. Escribirlo sin mirar Time:

1. El supervisor carga el cronograma del sector, con autor y fecha de cada
   cambio. Eso es el protocolo de reporte de cambio de turno, implementado como
   flujo: el acuerdo organizacional todavía no está, pero el software no lo
   necesita para existir.
2. Conciliación de fichadas contra el plan, con las diferencias marcadas.
3. El sistema **propone** la imputación —cambio de turno, licencia,
   enfermedad— y RRHH aprueba en lote. **Nunca imputa solo.**

### Los dos puertos

- `FuenteFichadas`: adaptador simulado con marcadas de prueba.
- `ExportadorNovedades`: el simulado deja la novedad en una bandeja de salida,
  en archivo. **Nada se escribe en Time.**

El adaptador real de Time se deja **sin terminar a propósito**, igual que
`legajos_nexus.py`, con un archivo que documente exactamente qué hay que pedirle
al proveedor de Time.

### La prueba de contrato

Replicar el patrón de `test_contrato_legajos.py`: un juego de pruebas que
describa qué espera el módulo de la fuente de fichadas. Cuando llegue el
diccionario de Time, esas pruebas contestan en una tarde si sirve o no, y la
traducción queda confinada al adaptador.

**Regla que acota el retrabajo:** ningún nombre de campo de Time aparece fuera
del adaptador. Si el diccionario llega y hay que tocar el dominio, algo se hizo
mal.

---

## Transversal a los tres

- **Un contrato de import-linter nuevo por módulo.** Se agrega antes del primer
  adaptador, no después. Pasan a ser doce.
- **README por módulo**, con la tabla de qué está simulado y qué es lo real, y
  la deuda técnica anotada. Un módulo sin deuda anotada está mal cerrado.
- **Ninguno toca** `apps/web` ni `apps/consulta`. Ninguno escribe en Nexus ni en
  Time.
- **Ninguno crea personas.** Legajos por el puerto existente, postulantes en
  Terceros.

---

## Lo que sigue sin hacerse

- Completar la matriz Puesto vs. EPP. La valida y firma Higiene y Seguridad.
- Reemplazar el papel antes del certificado de firma y del visto legal.
- La biblioteca documental: la está viendo Sandra con Cristian.
- Cualquier número presentado como conclusión mientras la fuente sea simulada.
  Se puede mostrar la pantalla; no se puede exportar el informe.
