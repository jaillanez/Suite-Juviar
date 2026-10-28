# Instrucciones de construcción para el agente

**Destinatario:** el agente que escribe el código de la suite ENAV / Jubiar.
**Se lee junto a:** `00_Base_Comun_Sistema_Unificado_ENAV_Jubiar_v04.md`,
`README_rrhh_epp.md`, `PLAN_DE_IMPLEMENTACION.md`.

Se trabaja **un paso por vez**. No se arranca el siguiente hasta que el anterior
cumple su criterio de terminado. Si un paso se traba por falta de un dato de la
empresa, se deja el puerto definido con un adaptador simulado y se sigue con el
paso siguiente; nunca se inventa el dato.

---

## 0. Reglas que no se negocian

Además de las siete reglas de la base común (§6.1), en todo paso:

1. **El dominio no importa framework ni base de datos.** `dominio/` sólo conoce
   modelos, puertos y reglas. Cada módulo nuevo agrega su contrato de
   import-linter antes de escribir la primera línea de adaptador.
2. **Todo lo que hoy es simulado se ve.** Franja roja en pantalla y marca de
   "sin validez legal" en cualquier documento, mientras la fuente no sea la
   real. Se saca cuando se enchufa lo real, no antes.
3. **Prueba negativa obligatoria** en todo lo que restrinja acceso o valide
   datos (§6.5): una prueba que intente la operación prohibida, un control
   negativo que confirme que la prueba falla cuando debe fallar, y los casos de
   campo vacío y campo nulo.
4. **Nada se borra.** Un CV que no califica se marca, no se descarta. Una
   entrega mal cargada se anula con motivo, no se elimina.
5. **Todo maestro nuevo declara su dueño** en la cabecera del YAML o de la
   tabla. Si no se puede nombrar al área responsable, el maestro está mal
   planteado y se para.
6. **Cada paso entrega:** código, pruebas, una línea en el README del módulo y
   la deuda técnica anotada en la tabla del README. Un paso sin deuda anotada
   es un paso mal cerrado.

**Sobre el orden.** La base común v0.4 pone Turnos como Etapa 1 y EPP como
Etapa 2. Este plan lo invierte, y no por capricho: turnos está bloqueado por el
diccionario de datos de Time, que todavía no tenemos, y EPP ya está construido y
en prueba. Cuando el orden se confirme, hay que actualizar §6.2 de la base común
para que los dos documentos no se contradigan.

---

## Ola 0 — Cerrar EPP

Punto de partida: `modulos/rrhh_epp` funcionando en prueba, 42 pruebas verdes.

### Paso 0.1 — Catálogo de dos niveles

**Es el paso más importante de toda la ola**, porque sin él la Ola 3 no existe.
Hoy el sistema registra "guante de nitrilo" (elemento del RD 068/11). Lo que
Compras necesita saber es *qué guante*: marca, modelo, color, talle.

- Agregar `ItemCatalogo` en `dominio/modelos.py`: código interno de ENAV (el
  1580 de la remera azul manga corta), marca, modelo, talle, color, y la
  referencia al elemento del RD 068/11 al que pertenece.
- Un elemento normativo tiene N ítems. La matriz Puesto vs. EPP sigue apuntando
  al **elemento**; la entrega registra el **ítem**.
- El operario del depósito elige el ítem de una lista filtrada por el elemento.
  Sigue sin poder escribir a mano (regla 3).
- Dueño del dato: Higiene y Seguridad, que es quien mantiene esa numeración.
- Cargar `datos/catalogo_items.yaml` en cuanto llegue el Excel de marcas. Hasta
  entonces, tres o cuatro ítems de muestra por elemento.

**Terminado cuando:** una entrega guardada permite responder "qué marca y modelo
de guante se llevó el legajo 1077 el 12 de marzo".

### Paso 0.2 — Constancia una por persona

Confirmado en la reunión: no sirve una lista con varios trabajadores. Una
planilla por persona.

- Generar el PDF con el formato del RD 062/11, un trabajador por documento.
- Renglones de reposición: cuando algo se rompe y se cambia, se agrega renglón a
  la constancia vigente, no se emite una nueva desde cero.
- Guardar el archivo original con sus metadatos (§5.4). Nada de regenerar el PDF
  para mostrarlo.

### Paso 0.3 — Los dos circuitos de entrega

- **Programada:** entrega estacional de convenio, verano e invierno, con fecha
  fija. El sistema arma la lista de quién tiene que recibir qué, por sector.
- **Espontánea:** por rotura o desgaste, permanente, de a una persona.
- La pantalla del depósito tiene que resolver los dos: entrega masiva en
  temporada y entrega de a uno el resto del año.

Falta el dato de cuántas personas se atienden por día en temporada alta (media
hora en el depósito, ver `ESTADO_Y_PEDIDO_MINIMO` §4). Mientras no esté, diseñar
para el caso masivo, que es el más exigente.

### Paso 0.4 — Stock del depósito

- Inventario por ítem, no por elemento.
- La entrega descuenta.
- Stock mínimo por ítem, definido por el depósito.
- **Proactivo:** al llegar al mínimo, el sistema genera el aviso a Compras. Hoy
  eso lo hace una persona acordándose.

### Paso 0.5 — Deuda técnica de la etapa 2

En este orden:

1. **PostgreSQL** en lugar de SQLite. Bloquea cualquier prueba con más de una
   tablet.
2. **Funcionamiento sin conexión** (regla 7): cola local en la tablet, envío
   diferido, y la entrega no se da por registrada hasta que el servidor
   confirma. Nunca se pierde en silencio.
3. **Identidad del operario de depósito**: hoy viene fijo en `"deposito"`.
   Depende del módulo de identidad de la base.
4. **PDF firmado** con el motor de firma real, cuando esté el certificado.

**La ola cierra cuando** una entrega real se hace desde el sistema, se imprime,
se firma, y la planilla de papel deja de llenarse a mano.

---

## Ola 1 — Selección de personal

Ruta nueva: `modulos/seleccion`. No toca Nexus, no toca Time, no necesita firma.
Se puede construir entera en paralelo a la Ola 0. **Tiene que estar usable en
noviembre.**

### Paso 1.1 — Decidir dónde vive el postulante

Antes de escribir código. Un postulante no es empleado (no tiene legajo) ni
tercero local (no tiene CUIT). Por la regla 1, **no se crea una cuarta lista de
personas**: se extiende el registro de terceros con el tipo `POSTULANTE`, clave
DNI cuando está, correo mientras no. Dueño del dato: RRHH.

Cuando un postulante entra a trabajar, no se convierte en empleado dentro del
sistema: se da de alta en Nexus y el postulante queda vinculado al legajo.

### Paso 1.2 — Ingesta

- Carpeta del servidor de Chimbas, donde ya están los PDFs guardados por las
  administrativas.
- Bandeja de correo, que es por donde llegan hoy.
- El archivo original se conserva siempre. Lo extraído es una capa encima, nunca
  un reemplazo.

### Paso 1.3 — Extracción

De cada CV: edad o fecha de nacimiento, nivel de estudios, experiencia, oficio,
localidad, contacto.

- Todo campo extraído se guarda marcado como **no verificado**, con el fragmento
  del texto del que salió.
- Nadie queda descartado por la extracción. Si un campo no se pudo leer, el CV
  va a una bandeja de revisión, no al fondo del ranking.

### Paso 1.4 — Filtros y ranking

Los filtros que pidieron: rango de edad, secundaria completa, perfil
(administración, mantenimiento, bodega).

- El resultado dice **por qué** cada CV quedó dentro o fuera. Un ranking sin
  explicación no se puede defender ni corregir.
- **Proactivo:** cuando entra un CV que encaja en una búsqueda abierta, avisa.

**Una advertencia que hay que dejar escrita en el módulo:** filtrar por edad es
una decisión de la empresa, no del sistema. El módulo registra quién definió
cada filtro y cuándo, y guarda el criterio junto con la búsqueda. Conviene que el
asesor legal mire el punto antes de la temporada.

**Terminado cuando:** una búsqueda de temporarios se resuelve sin abrir los PDFs
uno por uno.

---

## Ola 2 — Capacitaciones

Ruta nueva: `modulos/capacitacion`. Es el mismo patrón que EPP —planilla,
asistencia, firma— así que reutiliza el `MotorFirma` y sale barato después de la
Ola 0. No arrancar antes.

- **Tema** y **dictado**: el mismo tema dictado en tres tandas es un tema con
  tres dictados, no tres temas. Los porcentajes se calculan sobre el tema.
- Asistencia con firma del trabajador, con el mismo motor. La planilla se puede
  imprimir desde el sistema para firmar a mano donde no haya tablet.
- Reportes: % de asistencia por tema, % por persona, horas de capacitación por
  año y por legajo.
- **Proactivo:** el sistema marca solo a los supervisores con asistencia baja.
  Ese es el uso concreto que le quieren dar, no un reporte genérico.

---

## Ola 3 — Analítica de EPP para Compras

Ruta nueva: `modulos/epp_analitica`, **de sólo lectura** sobre lo que registra la
Ola 0. No arranca antes del tercer mes de uso real: sin entregas cargadas no hay
nada que analizar.

Depende enteramente del paso 0.1. Si el catálogo quedó en un solo nivel, esta ola
no se puede hacer.

- Duración real por ítem, cruzada por puesto y por sector.
- Consumo por período y costo por persona.
- **Reclamo de calidad registrado en la entrega**: cuando alguien devuelve algo
  roto, el operario marca el motivo en el momento. Es el dato que hoy se pierde y
  el que después no se puede reconstruir.
- Comparación entre dos ítems del mismo elemento: precio contra duración.

**Terminado cuando** se puede imprimir una hoja que diga, con números, que un
proveedor conviene menos que otro más caro.

---

## Ola 4 — Legajo digital y certificados médicos

Rutas nuevas: `modulos/legajo` y `modulos/salud`. Necesita la lectura de Nexus ya
resuelta en la Ola 0.

- Ficha por persona con los adjuntos escaneados. ENAV y Jubiar usan formatos de
  ficha distintos: el sistema guarda los mismos datos y emite el formato que
  corresponde a la empresa del legajo.
- Certificado médico con **diagnóstico**, que hoy no está en ningún sistema.
- **Proactivo:** aviso cuando se repite el mismo diagnóstico y se acerca el
  cómputo del año de licencia (art. 208 LCT).

**El diagnóstico es dato sensible de salud (Ley 25.326).** Va en `modulos/salud`,
separado del legajo general, con rol propio y bitácora de consulta: queda
registrado quién lo miró, no sólo quién lo cargó. Los reportes de estacionalidad
salen agregados, sin identificar a la persona. Esto no es una preferencia de
diseño; si se mezcla con el resto del legajo, después no se separa.

---

## Ola 5 — Conciliación de turnos

Ruta: `modulos/turnos`. **Bloqueado** hasta tener el diccionario de datos de
Time. No empezar a escribir adaptadores sobre tablas supuestas.

El problema no es informático: el supervisor cambia rotaciones y RRHH se entera
cuando el día ya salió con 8 horas extra y 8 ausencias. Por eso el módulo ataca
aguas arriba.

1. El supervisor carga el cronograma del sector en el sistema, donde ya toma la
   decisión hoy.
2. Conciliación automática de fichadas contra el plan, con las diferencias
   marcadas.
3. El sistema **propone** la imputación —cambio de turno, licencia,
   enfermedad— y RRHH aprueba en lote. Nunca imputa solo.
4. La corrección se exporta a Time. Time sigue siendo el sistema de asistencia;
   la suite no lo reemplaza.

Antes del código hace falta el **protocolo mínimo de reporte de cambio de turno**
del supervisor, ya listado en la base común §7.3. Sin ese acuerdo de proceso, el
módulo automatiza un circuito que nadie cumple.

---

## Lo que el agente no hace

- No toca `apps/web` ni `apps/consulta` desde estos módulos (contratos 8 y 9).
- No escribe en Nexus ni en Time. Lectura y exportación.
- No arranca la biblioteca documental: la está viendo Sandra con Cristian.
- No completa la matriz Puesto vs. EPP por su cuenta. La propuesta está hecha;
  la validación es de Higiene y Seguridad y va firmada por una persona.
- No reemplaza el papel antes de que estén el certificado de firma digital y el
  visto del asesor legal. Hasta entonces el sistema imprime y se firma a mano.
