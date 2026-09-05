# Suite Juviar — Estructura del proyecto

**Versión:** 0.1 · **Base normativa:** `00_Base_Comun_Sistema_Unificado_ENAV_Jubiar_v02.md`

Monolito modular con Domain-Driven Design. Un solo backend desplegable, dividido internamente en módulos que no se importan entre sí.

---

## 1. Los tres proyectos y sus módulos

La Base Común releva la información en tres proyectos. El código no se organiza por proyecto sino por módulo, y la correspondencia es esta:

| Proyecto de relevamiento | Dónde vive en el código | Módulos |
|---|---|---|
| **Base** (módulo 0) | `plataforma/` | identidad, terceros, firma, bitácora, outbox, parametría, cripto |
| **RRHH** | `modulos/` | turnos, rrhh_epp |
| **Sector Productivo** | `modulos/` + `apps/consulta` | cosecha, recepción, consulta pública |
| _(a definir, §7.1)_ | `modulos/ddjj` | declaración jurada — **bloqueado** |

La plataforma no es "un módulo más". Es la capa que todos pueden importar y que no importa a nadie: `plataforma → ✗ modulos` es un contrato verificado en CI. Los módulos de negocio, entre ellos, son independientes.

## 2. Las capas

Cada módulo tiene las mismas cuatro carpetas:

```
modulos/recepcion/
├── domain/          entidades y reglas. Python puro: sin SQLAlchemy, sin FastAPI, sin Pydantic
├── application/     casos de uso. Depende de puertos (Protocol), no de implementaciones
├── infrastructure/  SQLAlchemy y adaptadores externos. La única capa que conoce la base
└── api/             routers de FastAPI
```

Las dependencias van en una sola dirección: `api → application → domain`, con `infrastructure` implementando lo que `domain` define. Eso lo verifica `import-linter` en cada commit (`pnpm api:lint-arch`) y rompe el build si alguien lo viola. Los contratos están en `apps/api/pyproject.toml`:

1. Capas dentro de cada módulo y de cada servicio de plataforma.
2. Independencia entre los cinco módulos de negocio.
3. El dominio no importa `sqlalchemy`, `fastapi`, `asyncpg`, `redis` ni `pydantic`.
4. La aplicación no conoce implementaciones.
5. La plataforma no depende de los módulos.

## 3. Comunicación entre módulos

Un módulo nunca importa a otro. Se comunican por eventos de dominio con patrón **outbox**: el evento se escribe en la misma transacción que el cambio de estado, y un worker (`workers/outbox_worker.py`) lo entrega con reintentos y backoff exponencial. Un evento que agota los reintentos queda `FALLIDO` y visible en el panel; nunca desaparece en silencio.

Cuando algo necesita cruzar módulos, vive en `composicion/`, el único lugar autorizado a conocer varios a la vez. Hoy hay dos:

- **`entrega_epp.py`** — cruza identidad (cabecera del RD 062/11 traída de Nexus), rrhh_epp (catálogo RD 068/11) y firma. Es el equivalente estructural del "canje" del proyecto de referencia: el flujo que toca tres dueños de dato distintos.
- **`recepcion_uva_terceros.py`** — cruza recepción con el registro de terceros por la responsabilidad solidaria de la Ley 9133 de Mendoza.

## 4. El stack

- PostgreSQL 18.6 con PostGIS, Python 3.14, FastAPI, SQLAlchemy 2 asincrónico, Alembic, Redis
- Next.js 16 con React 19, Tailwind 4 y shadcn/ui
- Monorepo con pnpm: `apps/api`, `apps/web`, `apps/mobile`, `apps/consulta`, más paquetes compartidos
- Una sola app móvil con Capacitor 8.5.1 y tres perfiles adentro: **campo** (capataz: fichaje y tareaje en el cuartel), **depósito** (entrega de EPP con firma en tablet) y **báscula** (romaneos en la playa de descarga)

El perfil móvil lo resuelve el backend a partir del puesto y sector del legajo. No lo elige el usuario.

**PostGIS** entra por dos usos concretos: geometría de fincas y cuarteles para la trazabilidad de origen de cada romaneo, y geolocalización de las firmas capturadas en tablet (refuerzo previsto en §5.4, no imprescindible para el MVP).

## 5. Las decisiones que más forma le dieron

**Dos roles de base de datos.** `sj_owner` migra y es dueño del esquema; `sj_app` corre la aplicación y no puede crear ni alterar tablas (`sql/00_roles.sql`).

**La bitácora es inmutable a nivel del motor.** Al rol de aplicación se le revocan `UPDATE` y `DELETE` sobre el schema `bitacora` (`sql/10_bitacora_inmutable.sql`). No depende de que el código se porte bien: aunque alguien escriba SQL crudo, PostgreSQL lo rechaza. Lo mismo aplica a los documentos firmados, porque un PDF con firma re-guardado pierde validez.

**Datos personales en dos columnas.** Un HMAC-SHA256 con clave secreta para buscar e indexar, y el valor cifrado con AES-256-GCM aparte. La clave del HMAC vive fuera de la base. Si aparece una columna `dni text` en claro, es un bug de esquema.

**Reglas críticas imposibles de violar por construcción, no por convención:**

| Regla de la Base Común | Cómo se hace imposible violarla |
|---|---|
| §3.1 Ningún módulo crea ni edita personal; Nexus es el dueño | `RepositorioLegajos` no declara `guardar` ni `crear`. No es que no se use: no existe. `Legajo` es `frozen` |
| §3.2 Los dos registros de identidad nunca se mezclan | `Romaneo` referencia productor por CUIT y chofer por DNI. No hay campo donde poner un legajo |
| Recepción registra qué entró, no qué se paga | El módulo `recepcion` no tiene campos de precio, liquidación ni saldo |
| §5.4.1 Conservar el archivo original | `DocumentoFirmado` es `frozen` y su repositorio no tiene `actualizar`. Corregir = emitir uno nuevo que anule al anterior |
| El peso de báscula es un hecho, no un campo | `Pesada` es `frozen` y `Romaneo` no expone setters de peso. Una corrección genera un contra-romaneo que referencia al original |
| §4.3 El bot solo ve lo mínimo | El modelo de lectura del bot no tiene DNI, ni legajo, ni precio, ni saldo. Si se compromete, lo que se filtra son kilos y un número de romaneo |
| §6.1.3 Sin texto libre donde hay catálogo | `ItemEntregado` guarda un código del RD 068/11; no acepta descripción libre |

**Parametría.** Todo lo que puede cambiar sin desarrollo vive en `plataforma/parametria`, editable desde el panel: tolerancias de peso, plazos de aviso de recambio de EPP, tolerancia de desvío de turnos, vigencia del código de acceso al bot.

## 6. Dos puntos donde la estructura se aparta del molde

Vale la pena que los mires antes de aprobar, porque son desvíos deliberados de lo que pediste.

**El bot no entra en "un solo backend desplegable".** La regla §4.3 dice que el bot vive en DMZ, nunca consulta la base de producción y es de solo lectura. Un módulo dentro del monolito no puede cumplir eso: comparte proceso, red y conexión a la base. Por eso está como segundo deployable, `apps/consulta`, con su propio `pyproject.toml` que deliberadamente **no** depende del paquete de la API. Si algún día lo importa, el bot pasó a tener acceso al dominio completo. Sigue siendo un monolito modular más un satélite de lectura, no un microservicio.

**Hay dos motores de base de datos, no uno.** El stack pide PostgreSQL 18.6, pero Nexus corre sobre SQL Server en Santa Fe y §4.2 decidió acceder por Vistas y Stored Procedures vía VPN, no por API REST. Entonces: PostgreSQL es la base de la suite, y SQL Server es una fuente externa de solo lectura a la que se llega con un engine aparte (`SJ_NEXUS_DSN`). El repositorio de legajos es el único componente que la toca.

## 7. Orden de construcción

El orden es por dependencia técnica, no por urgencia percibida (§6.2):

```
Etapa 0  plataforma/    WAN punto a punto · vistas SQL sobre legajos · registro de
                        terceros · motor de firma · bitácora · outbox
Etapa 1  turnos         retorno más rápido y visible: mata el Excel de desvíos
Etapa 2  rrhh_epp       necesita firma + catálogo RD 068/11 + matriz Puesto vs. EPP
Etapa 3  cosecha        necesitan terceros + maestro de sectores. En producción
         recepcion      ANTES de vendimia, no durante
Etapa 4  apps/consulta  capa de lectura sobre recepción. Sin etapa 3 no informa nada
Etapa 5  ddjj           según qué DDJJ sea; reutiliza el motor de firma
```

`modulos/ddjj/domain/entidades.py` está vacío a propósito, con la explicación adentro. Modelar una DDJJ "provisionalmente" arrastra al esquema de firma y a la retención legal.

## 8. Qué falta para escribir código de verdad

Estas definiciones bloquean partes concretas del scaffold:

| Definición pendiente | Qué bloquea |
|---|---|
| Razón social y CUIT de cada unidad (ENAV / ANAP / Jubiar) | Si `NumeroLegajo` es único global o único por empresa |
| Método de firma del trabajador (tablet / PIN / biometría) | El adaptador de `MotorDeFirma` y la pantalla de depósito |
| Qué es la declaración jurada | El módulo entero |
| Autenticación y canal del bot | `apps/consulta/api/router.py`, hoy devuelve 501 |
| Verificación documental del productor (Ley 9133) | Si `recepcion_uva_terceros` bloquea o solo advierte |
| Si la báscula tiene salida digital | El adaptador `LectorBascula` |
| Diccionario de datos de Time | El módulo de turnos |
| Credenciales de la VPN a Santa Fe | Todo lo que lee legajos |
| Catálogo RD 068/11 y matriz Puesto vs. EPP | El módulo de EPP |

## 9. Cómo se corre

```bash
pnpm install
psql -v owner_password=... -v app_password=... -f sql/00_roles.sql
psql -f sql/10_bitacora_inmutable.sql

pip install -e "apps/api[dev]"
cd apps/api && alembic upgrade head

pnpm api:lint-arch    # contratos de arquitectura
pnpm api:dev          # API en :8000
pnpm api:worker       # worker de outbox
pnpm dev:web          # panel en :3000
```
