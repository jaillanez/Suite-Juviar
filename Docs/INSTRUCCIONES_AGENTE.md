# Instrucciones para el agente — dejar funcional el módulo RRHH / EPP

**Repositorio:** `Suite-Juviar`
**Rama base:** `codex/rrhh-epp-unificado` (último commit `61de1b3`)
**Fuente de lo nuevo:** paquete `rrhh_epp_mvp` (entregado aparte)

Desde `61de1b3` hubo cambios que **no están en el repositorio**. Este documento
los ordena por dependencia. Cada tarea tiene criterio de aceptación; ninguna se
da por terminada sin él.

Reglas que valen para todo el trabajo, sin excepción:

- El dominio no importa `adaptadores` ni `api`. Los nueve contratos de
  import-linter tienen que seguir pasando en cada tarea, no sólo al final.
- Ningún dato inventado entra sin marca de estado. Todo lo que no validó la
  empresa lleva `PROVISORIO` o `PROPUESTA_SIN_VALIDAR` y se ve en pantalla.
- Un permiso escrito no es un permiso verificado (§6.5 de la base común). Toda
  restricción nueva lleva una prueba que **intenta la operación prohibida** y un
  control negativo que confirme que esa prueba falla cuando tiene que fallar.
- No tocar `apps/web`, `infra/` ni el sitio público. Nada de esto lo requiere.

---

## Tarea 1 — Catálogo real RD 068/11

**Qué hay hoy:** un catálogo de muestra con códigos inventados.
**Qué va:** los 145 elementos reales del RD 068/11 V 02 (septiembre 2023).

1. Copiar `herramientas/importar_rd068.py` a `apps/api/tools/` (o donde la suite
   tenga las utilidades de carga). Requiere `xlrd` sólo para el import, no en
   runtime: que quede como dependencia de desarrollo, no de la API.
2. Copiar `datos/catalogo_rd068.yaml` generado. **No editarlo a mano**: la
   cabecera lo dice y cuando salga la V 03 se regenera con un comando.
3. El campo `codigo` es ahora el N° de Orden real de ENAV, y es texto, no
   entero: existe `104-B`. Revisar que ninguna parte del código asuma numérico.
4. Los campos nuevos del elemento son `familia`, `destino_declarado` y
   `criterio_vida_util`. Agregarlos al modelo de dominio con valor por defecto,
   para no romper lo que ya construye elementos.

**Aceptación:** el catálogo carga 145 elementos; existe el código `104-B`; una
prueba verifica que un código con sufijo no rompe el ordenamiento (`114` va
después de `9`, no antes).

---

## Tarea 2 — La matriz pasa a ser por sector + puesto

Esta es la que toca el dominio. **Es la única tarea con cambio de contrato**, así
que va antes que las demás y sola en su commit.

**Por qué:** ENAV organiza el EPP por sector desde 2012, no por puesto. El
puesto agrega lo suyo encima.

1. Reemplazar en el puerto `RepositorioCatalogo`:
   `requisitos_de_puesto(puesto_codigo)` → `requisitos_de(sector_codigo, puesto_codigo)`.
   Agregar `sector_definido(sector)`, `nombre_sector(sector)` y `aplica_base(sector)`.
2. `RequisitoEPP` suma dos campos: `fundamento` (por qué esa línea existe) y
   `origen` (`BASE`, `SECTOR` o `PUESTO`). Los dos se muestran en pantalla.
3. Reglas de composición, tal como están en `catalogo_yaml.py`:
   - base operativa + sector + puesto;
   - si un código aparece en dos niveles gana el más específico;
   - a igual nivel, gana la **cantidad mayor**. Nunca se entrega de menos por un
     solapamiento de la matriz;
   - un sector que no está en la matriz igual recibe la base operativa. Viña no
     figura en el esquema de 2012 y un cosechero no puede quedar sin nada.
4. Copiar `datos/matriz_sector_puesto_epp.yaml` (184 líneas, 19 sectores + 4
   puestos). Mantener `estado: PROPUESTA_SIN_VALIDAR`.
5. Portar la pantalla `/matriz`: es de sólo lectura y es lo que va a mirar
   Higiene y Seguridad para aprobar. Que quede detrás del perfil que
   corresponda, pero **sin botón de aprobar**: aprobar necesita identidad real y
   todavía no la hay.

**Aceptación:** las pruebas de `tests/test_matriz.py` del paquete pasan dentro de
la suite. En particular las tres que no son de camino feliz: la faja lumbar no
aparece en ninguna combinación de sector y puesto, el dieléctrico nunca sale sin
su sobreguante, y un sector sin matriz igual recibe la base.

---

## Tarea 3 — Vida útil y auditoría del catálogo

1. Copiar `datos/vida_util_referencial.yaml`. Es una tabla que armamos nosotros
   investigando normativa; el RD 068/11 no la trae. Estado
   `REFERENCIAL_INVESTIGADO`, no confirmado por HyS.
2. El adaptador de catálogo la aplica al cargar: primero busca excepción por
   código, después por familia. `vida_util_dias: null` es válido y significa que
   ese elemento no tiene régimen de vencimiento (caso de la faja lumbar, que no
   es EPP).
3. Portar `alertas()`. Hoy detecta 27 elementos con problemas: sin marca, sin
   tipo/modelo, sin certificación en familia crítica, y **certificación citando
   referencias derogadas** por la Res. SIC 18/2025, que eliminó el sello "S" y
   reemplazó a la Res. 896/99. Cuidado al portar la comparación: las comillas del
   Excel son tipográficas, no rectas, y hay que normalizarlas o la detección no
   dispara.
4. Exponer las alertas en la API y mostrar el conteo en `/matriz`. No frenan
   ninguna entrega: son avisos.

**Aceptación:** el sistema marca los códigos 12, 13 y 25 sin marca; los seis
calzados y el guante 128 con referencia derogada; el casco 84 con 1825 días; el
dieléctrico 71 con 180 días y su criterio citando la IEC 60903.

---

## Tarea 4 — Rehacer `perfiles_acceso.yaml`

El archivo que quedó en `plataforma/parametria/data/` mapea puesto/sector a
perfil, pero se escribió antes de que supiéramos los sectores reales. Hoy
probablemente apunta a sectores que no existen en Nexus.

1. Rehacerlo contra los 19 sectores reales: `BOD COL CLA FIL CON EFL FVA ENV LIM
   MEC ELE CAL LAB ADM BAS MAE PAN LAG PRE`.
2. Ojo con dos cosas que todavía no están confirmadas y hay que dejar anotadas
   en el archivo, no resueltas por las malas:
   - el esquema de HyS tiene **Pañol** y no tiene **Depósito**, y la operación
     habla de depósito. Puede ser el mismo lugar con dos nombres;
   - **Viña no está** entre los 19: el esquema de 2012 sólo cubre bodega.
3. Que un sector desconocido **no** derive en un perfil por defecto con permisos.
   Sin mapeo, sin perfil: el usuario ve el error, no una pantalla que no le
   corresponde.
4. Mantener dueño `Recursos Humanos` y estado `PROVISORIO`.

**Aceptación:** una prueba verifica que todo sector del YAML de perfiles existe
en la matriz de EPP o está explícitamente declarado como fuera de ella; y una
prueba negativa confirma que un sector inventado no obtiene perfil.

---

## Tarea 5 — Funcionamiento sin conexión (regla 7)

Es lo único pendiente que puede hacer **perder una entrega ya firmada**: se corta
la red en el depósito, el operario da por hecho que quedó registrada, el
trabajador se fue con los guantes y no hay constancia de nada.

**Decisión de diseño, tomada:** la tablet guarda localmente y sincroniza después.
La alternativa —negarse a operar sin red— suena más segura pero en la práctica
empuja al operario a entregar igual y anotar en un papel, que es exactamente el
problema que este sistema viene a eliminar.

Como esa decisión abre el riesgo de entregas que nunca lleguen al servidor, va
con estas reglas duras:

1. La entrega se guarda en cola local con todo lo necesario para reconstruirla:
   legajo, líneas, firma, sello de tiempo del momento real de la entrega (no el
   de la sincronización) y quién la registró.
2. **La constancia no se emite hasta que el servidor confirmó.** En pantalla dice
   "pendiente de sincronizar", no "registrada".
3. La pantalla muestra siempre cuántas entregas hay sin sincronizar. Si hay una
   sola, se ve.
4. La aplicación **se bloquea** para nuevas entregas al superar un umbral —
   sugerido: 20 pendientes o 24 horas sin sincronizar — y avisa que hay que
   recuperar la conexión. Una cola que crece sin límite es una pérdida de datos
   con pasos intermedios.
5. Reintento con espera creciente. La sincronización es idempotente: cada entrega
   lleva su identificador generado en la tablet, y reenviarla dos veces no puede
   generar dos registros.

**Aceptación** (todas negativas, que son las que importan acá):

- cortar la red a mitad de una entrega y verificar que no se pierde;
- reenviar la misma entrega dos veces y verificar que queda **una** sola;
- confirmar que con entregas pendientes la constancia **no** se emite;
- superar el umbral y verificar que la aplicación se bloquea;
- control negativo: desactivar el guard del umbral y comprobar que esa última
  prueba falla. Si pasa igual, no está midiendo nada.

---

## Tarea 6 — PDF firmado (después de la 5, no antes)

Depende del motor de firma real de `plataforma/firma`, que todavía no existe.
Cuando esté:

- generar el PDF con el formato exacto del RD 062/11;
- **conservar el archivo original con metadatos e integridad de firma intactos**.
  Una impresión, una captura o un PDF re-guardado destruyen la firma y le quitan
  validez. Esto es lo que se presenta en una inspección;
- sello de tiempo en cada firma;
- recién ahí quitar la marca de "documento sin validez legal".

---

## Lo que NO hay que hacer

- No quitar la franja de entorno de prueba ni la marca de constancia sin validez
  legal mientras la fuente de legajos sea el archivo. Es a propósito: tiene que
  verse de lejos que eso no se presenta en una inspección.
- No cambiar `estado: PROPUESTA_SIN_VALIDAR` de la matriz. Lo cambia la empresa
  cuando Higiene y Seguridad la firme, no el agente.
- No agregar la faja lumbar (código 33) a la matriz. Está en el catálogo porque
  la empresa la compra, pero no es un EPP y computarla como protección debilita
  la defensa ante una inspección.
- No proponer protección respiratoria con filtro para el CO2 de Lagares. Ningún
  filtro protege contra desplazamiento de oxígeno. Eso se resuelve con el
  procedimiento de espacio confinado (Res. SRT 953/2010 + IRAM 3625), que no es
  un EPP de entrega individual.
- No completar `_conectar()` de `legajos_nexus.py` con datos inventados. Sin VPN
  ni Vista, esa clase queda como está y falla con un mensaje claro.

---

## Orden y commits

Un commit por tarea, en este orden: 1, 2, 4, 3, 5. La tarea 2 va sola porque
cambia el contrato del puerto. La 6 espera al motor de firma.

Subir `codex/rrhh-epp-unificado` al remoto antes de empezar, aunque nadie la
revise todavía. Una tarde de trabajo colgando de una sola máquina es riesgo
gratis.
