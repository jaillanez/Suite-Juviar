# Base Común del Sistema Unificado — ENAV S.A. y Jubiar

**Versión:** 0.3
**Uso:** este documento se copia sin modificar en todos los proyectos de trabajo. Si algo cambia acá, se actualiza en todos.

**Cambios respecto de la v0.2:** se incorpora la estructura de código construida y las decisiones de arquitectura tomadas durante la implementación de la base.

---

## 1. Para qué sirve este documento

El sistema va a ser **una sola aplicación** con varios módulos, aunque la información se releve en proyectos separados. Este documento define lo que todos los módulos comparten y que, por lo tanto, no puede decidir cada área por su cuenta:

1. Quién es quién en el sistema (empleados y terceros).
2. Cómo se conectan los sistemas y dónde viven los datos.
3. Cómo se firma un documento y qué validez legal tiene.
4. En qué orden se construye y qué reglas cumple todo módulo nuevo.

Todo lo demás (matriz de EPP, esquemas de turno, enología, logística de vendimia) es específico de cada módulo y va en su propio proyecto.

---

## 2. Mapa de módulos

| # | Módulo | Qué resuelve | Proyecto donde se releva | Ruta real en el código |
|---|---|---|---|---|
| 0 | **Base transversal** | Identidad, conexión, firma, bitácora | Base | `plataforma/identidad`, `plataforma/terceros`, `plataforma/firma`, `plataforma/bitacora`, `plataforma/outbox`, `plataforma/parametria`, `plataforma/cripto` |
| 1 | **RRHH / Higiene y Seguridad** | Legajos, EPP, licencias médicas, reclutamiento | RRHH | `modulos/rrhh_epp` |
| 2 | **Turnos y asistencia** | Turnos rotativos, novedades, sincronización Time ↔ Nexus | RRHH (con insumo de Producción) | `modulos/turnos` |
| 3 | **Cosecha y personal temporario** | Alta masiva estacional, corresponsabilidad gremial, EPP de temporarios | Productivo + RRHH | `modulos/cosecha` |
| 4 | **Descarga de camiones** | Recepción de uva: pesaje, romaneo, productor, transportista | Productivo | `modulos/recepcion` |
| 5 | **Bot de consulta** | Consulta externa del estado de descargas | Productivo | `apps/consulta` |
| 6 | **Declaración jurada** | Formulario declarativo con firma y resguardo legal | A definir (ver §7) | `modulos/ddjj` |

El módulo 0 no es un módulo más: es la base sobre la que se apoyan los otros seis. Nada se construye antes que él.

---

## 3. Identidad: dos registros, nunca mezclados

Hasta la v0.1 el sistema tenía un solo tipo de usuario: el empleado. Con el bot de consulta y la descarga de camiones aparece un segundo tipo, y **no puede vivir en la misma tabla**.

### 3.1 Personas internas — el legajo de Nexus

**Regla: el legajo de Nexus es la clave única de todo empleado.**

Ningún módulo crea, edita ni guarda su propia lista de personal. Todos leen de Nexus.

| Dato | Origen | Se edita en |
|---|---|---|
| Número de legajo | Nexus | Nexus |
| Nombre y apellido | Nexus | Nexus |
| DNI | Nexus | Nexus |
| Puesto de trabajo | Nexus | Nexus |
| Sector / unidad | Nexus | Nexus |
| Empresa (ENAV / Jubiar) | Nexus | Nexus |

Consecuencia práctica: cuando el sistema genere la constancia de entrega de EPP, los campos de **Nombre, DNI y Puesto** de la cabecera del RD 062/11 se traen automáticamente de Nexus. No se tipean a mano.

El personal temporario de cosecha entra por este mismo maestro, con una marca de tipo de vínculo. No se maneja en una planilla aparte.

### 3.2 Terceros externos — productores y transportistas

El productor que entrega uva y el chofer que trae el camión **no son empleados** y no tienen legajo. Necesitan su propio registro:

| Dato | Clave |
|---|---|
| Productor / entregador | CUIT |
| Transportista / empresa de flete | CUIT |
| Chofer | DNI |
| Vehículo | Patente (chasis y acoplado) |

**Regla: los dos registros nunca se mezclan.** Un mismo DNI puede ser empleado y chofer de un tercero; son dos entidades distintas del sistema con permisos distintos.

### 3.3 El puente entre los dos registros

Hay un punto donde se tocan, y es de riesgo legal: bajo la **Ley 9133** de Mendoza, si la bodega procesa uva de terceros sin verificar la registración y la entrega de EPP de los trabajadores de ese productor, puede ser declarada **solidariamente responsable** de sus multas y obligaciones laborales.

Esto significa que el módulo de descarga de camiones no es solo logística: en el momento de recibir uva de un tercero, el sistema debería poder dejar constancia de la verificación documental del productor. **A definir con el asesor legal** qué se exige y qué se registra.

### 3.4 Punto a confirmar antes de programar

En la documentación aparecen indistintamente **ENAV** y **ANAP** como unidad periférica junto a Jubiar. Hay que confirmar la razón social correcta de cada unidad y si el sistema maneja dos CUIT separados (ENAV S.A. figura con CUIT 30-69313567-9). Esto define si el legajo es único global o único por empresa.

---

## 4. Infraestructura: dónde vive cada cosa

### 4.1 Situación actual

- **Servidor central de Nexus:** Santa Fe. Es el núcleo de datos.
- **Unidades periféricas:** Jubiar y la segunda unidad (ver §3.4).
- **Servidor local:** Chimbas. Hoy las administrativas guardan ahí PDFs escaneados de facturas y currículums, de forma manual.
- **Conectividad:** túneles VPN entre sedes.
- **Time ↔ Nexus:** existe sincronización de legajos, pero la auditoría de desvíos de turnos rotativos todavía se hace en Excel.

### 4.2 Decisión de arquitectura para el MVP

Se adopta **acceso directo a base de datos vía VPN, con Vistas (Views) y Procedimientos Almacenados (Stored Procedures) en SQL Server**, en lugar de arrancar con una API REST.

Fundamento:
- Aprovecha la VPN que ya existe, sin exponer la red a internet.
- Las Vistas permiten que cada módulo consulte **solo** los campos que necesita.
- Los Stored Procedures evitan permisos de escritura directa sobre las tablas base y dejan bitácora auditable.
- Menor costo y menor tiempo de puesta en marcha.

La implementación trabaja con **dos motores de base de datos**: PostgreSQL 18.6 es la base propia de la suite y SQL Server, donde corre Nexus en Santa Fe, queda como fuente externa de solo lectura a través de la VPN. El repositorio de legajos es el único componente que toca Nexus; ningún otro módulo accede directamente a ese motor.

### 4.3 La excepción: el bot de consulta

El bot rompe este esquema y hay que tratarlo aparte. Es el **único componente que atiende usuarios fuera de la red de la empresa** (productores y transportistas consultando desde su celular).

Por eso quedó construido como un segundo desplegable en `apps/consulta`, con dependencias propias que, a propósito, no incluyen el paquete de la API. La separación de proceso, red y dependencias hace que las cinco reglas siguientes ya no dependan de una convención: se cumplen estructuralmente.

Reglas no negociables para el bot:

1. **Nunca consulta la base de producción directamente.** Lee de una base o vista intermedia, separada, con solo los datos que necesita mostrar.
2. **Es de solo lectura.** El bot informa; no da de alta, no modifica, no confirma nada.
3. **Vive en zona desmilitarizada (DMZ),** no dentro de la red donde está Nexus.
4. **Cada consulta queda registrada:** quién preguntó, qué preguntó, cuándo.
5. **Muestra solo lo del propio consultante.** Un productor ve sus descargas, no las del vecino. Esto exige resolver cómo se autentica: código de operación, CUIT + clave, o número de romaneo.

Si el bot se construye sin estas cinco reglas, se convierte en la puerta de entrada a toda la base de datos de la empresa.

### 4.4 Definiciones técnicas pendientes

- Parámetros y credenciales de la VPN al servidor de Santa Fe.
- Capacidad, backup y seguridad del servidor de Chimbas.
- Diccionario de datos de Time: en qué tablas se inyectan marcadas, ausencias y novedades de turno.
- Canal del bot: WhatsApp, Telegram, web o SMS. Define costo, proveedor y tiempos.
- Origen del dato de peso: si la báscula tiene salida digital o la carga es manual.

---

## 5. Firma y validez legal

Marco aplicable: **Ley 25.506** (firma digital) y **Disposición SRT 3/2022** (habilita reemplazar la planilla de papel de la Resolución SRT 299/2011 por constancia digital).

### 5.1 Esquema mixto

| Quién firma | Tipo de firma | Cómo |
|---|---|---|
| **La empresa** (representante legal / responsable de HyS) | Firma **digital** | Certificado de entidad certificante licenciada por el Estado |
| **El trabajador** | Firma **electrónica** | Trazo en tablet, PIN personal o validación biométrica |

Darle un certificado con token a cada operario es inviable por costo y burocracia. La normativa permite firma electrónica del trabajador, siempre que haya vínculo unívoco entre la firma, el documento y su legajo.

### 5.2 Método de firma del trabajador — a definir

Elegir uno o combinarlos, con el asesor legal:

1. **Firma táctil en tablet** en el depósito, al momento de la entrega.
2. **PIN personal** vinculado al legajo de Nexus.
3. **Validación biométrica** por reconocimiento facial.

### 5.3 La firma es un servicio compartido, no una función del módulo de EPP

Esto es importante para la construcción: la constancia de EPP, la declaración jurada y cualquier conformidad futura usan **el mismo motor de firma**. Se programa una vez, en la base, y todos los módulos lo invocan.

Si cada módulo implementa su propia firma, van a convivir tres criterios de validez legal distintos y ninguna auditoría va a resultar defendible.

### 5.4 Reglas técnicas obligatorias

Valen para **cualquier** documento firmado del sistema:

1. **Conservar el archivo original.** El PDF firmado se guarda con metadatos e integridad de firma intactos. Una impresión, una captura de pantalla o un PDF re-guardado destruyen la firma y le quitan validez.
2. **Sello de tiempo.** Cada firma lleva certificación cronológica del momento exacto.
3. **Permisos acotados.** Acceso restringido al legajo digital, con registro de quién consultó, aprobó o registró cada operación.

A evaluar como refuerzo (no imprescindible para el MVP): cadena de auditoría basada en hashes y geolocalización en firmas capturadas en tablet.

---

## 6. Instrucciones de construcción

### 6.1 Las siete reglas que cumple todo módulo

Cualquier módulo nuevo, sin excepción:

1. **No inventa personas.** Empleados salen de Nexus; terceros, del registro de terceros. Ningún módulo crea su propia lista.
2. **No escribe directo en las tablas de Nexus.** Todo pasa por Vistas y Stored Procedures.
3. **No usa texto libre donde hay catálogo.** Si existe un maestro (EPP, sectores, productores, variedades), el usuario selecciona de una lista.
4. **Usa el motor de firma de la base.** No implementa el suyo.
5. **Deja bitácora.** Quién hizo qué y cuándo, en toda operación que cree o modifique datos.
6. **Define su dueño del dato.** Cada tabla maestra tiene un área responsable de mantenerla. Si no se puede nombrar al dueño, el maestro está mal planteado.
7. **Funciona sin conexión o falla de forma clara.** En depósito, báscula y viña la red se cae. El módulo espera y reintenta, o avisa; nunca pierde el registro en silencio.

Estas siete reglas se verifican en integración continua con **import-linter**, mediante siete contratos de arquitectura. Si alguien introduce una dependencia que las viola, el build se rompe antes de integrar el cambio.

La operación móvil se concentra en **una sola aplicación** con tres perfiles internos: **campo** (fichaje y tareaje), **depósito** (entrega de EPP con firma) y **báscula** (pesadas y romaneos). El perfil corresponde al puesto y sector del legajo; no lo elige el usuario.

### 6.2 Orden de construcción

El orden no es por urgencia percibida sino por dependencia técnica. Un módulo no arranca hasta que lo que está arriba de él funciona.

**Etapa 0 — Base transversal.** Conexión WAN punto a punto. Vistas SQL sobre el maestro de legajos. Registro de terceros. Motor de firma. Bitácora. *Sin esto, todo lo demás se construye sobre arena.*

**Etapa 1 — Turnos y asistencia.** Es el que tiene el retorno más rápido y más visible: elimina el Excel de auditoría de desvíos y corta las diferencias de 8 horas. Usa el legajo, no necesita firma. Buen primer módulo real.

**Etapa 2 — RRHH / EPP.** Necesita: legajo + motor de firma + catálogo RD 068/11 digitalizado + matriz Puesto vs. EPP. Es el módulo con más peso normativo, y el que baja el riesgo de multa.

**Etapa 3 — Cosecha y descarga de camiones.** Necesita: registro de terceros + maestro de sectores productivos. Se construye junto porque comparten los mismos actores. Ojo con la estacionalidad: hay que estar en producción **antes** de vendimia, no durante.

**Etapa 4 — Bot de consulta.** No se puede construir antes que la etapa 3: un bot sin datos que consultar no sirve de nada. Es una capa de lectura sobre la descarga de camiones.

**Etapa 5 — Declaración jurada.** Se ubica según qué DDJJ sea (ver §7). Si es un documento firmado, reutiliza el motor de firma de la etapa 0 y es de las cosas más rápidas de sumar.

### 6.3 La trampa a evitar

El bot es lo más vistoso y lo que más rápido se pide, porque se ve funcionando en un celular. Pero es lo **último** de la cadena: sin descarga de camiones digitalizada no tiene nada que informar, y construido apurado es el mayor agujero de seguridad del sistema.

Mismo criterio para el resto: lo que se ve no es lo que sostiene.

### 6.4 Criterio de "terminado"

Un módulo está listo cuando, además de funcionar:

- El proceso viejo se dio de baja (no conviven el sistema y el Excel).
- El usuario real lo usó una semana sin asistencia del desarrollador.
- Se puede exportar la evidencia que pediría una inspección.
- Está documentado quién es el dueño de cada maestro que usa.

---

## 7. Definiciones pendientes

### 7.1 Prioritarias

- [x] **Arquitectura de acceso.** Acceso a Nexus por Vistas y Stored Procedures en SQL Server vía VPN; PostgreSQL 18.6 como base propia de la suite.
- [x] **Motor de firma como servicio compartido.** Vive en la base transversal y es invocado por los módulos que generan documentos firmados.
- [ ] **Qué es la declaración jurada.** El término se usa para cosas muy distintas: DDJJ de existencias y cosecha ante el INV, DDJJ de salud o domicilio del empleado, DDJJ de carga del transportista. Cada una tiene otro firmante, otro destinatario y otro plazo legal. Sin esto no se puede ubicar el módulo.
- [ ] **Quién consulta el bot y qué puede ver.** Productores, transportistas o ambos. Define autenticación y canal.
- [ ] **Verificación documental del productor tercero** (Ley 9133). Qué se exige y qué queda registrado.
- [ ] Confirmar razones sociales y CUIT de cada unidad (ENAV / ANAP / Jubiar).
- [ ] Elegir método de firma electrónica del trabajador (tablet / PIN / biometría).

### 7.2 Insumos a conseguir

- [ ] Catálogo RD 068/11 completo, para digitalizar.
- [ ] Matriz Puesto vs. EPP, del área de Higiene y Seguridad.
- [ ] Diccionario de datos de la base de Time.
- [ ] Credenciales y parámetros de la VPN al servidor de Santa Fe.
- [ ] Relevamiento de capacidad y seguridad del servidor de Chimbas.
- [ ] Maestro de sectores y puestos del área productiva.
- [ ] Protocolo mínimo de reporte de cambio de turno del supervisor.
- [ ] Circuito actual de descarga: qué se anota hoy, en qué papel, quién lo firma.
