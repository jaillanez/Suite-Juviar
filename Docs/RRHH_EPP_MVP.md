# RRHH / Higiene y Seguridad — entrega de EPP

Etapa 2 de la Suite Juviar. Digitaliza el formulario RD 062/11 con
conformidad del trabajador en tablet, dentro del backend y la aplicación móvil
únicos de la suite.

## Acceso por perfil

El usuario no elige una pantalla. El backend toma el legajo declarado, busca
puesto y sector y resuelve el perfil desde Parametría antes de autorizar cada
endpoint:

| Perfil | Función móvil | Acceso a EPP |
|---|---|---|
| `campo` | Fichaje y tareaje | No |
| `deposito` | Entrega y firma de EPP | Sí |
| `bascula` | Pesadas y romaneos | No |

Mientras no esté operativo el login de `plataforma/identidad`, el desarrollo
local usa el encabezado `X-Legajo-Usuario`. **No es autenticación ni sesión:**
es una declaración de identidad que cualquiera puede suplantar. Por lo tanto,
la bitácora registra quién dijo ser el operador, no quién fue realmente.

El adaptador viene deshabilitado, exige
`SJ_HABILITAR_IDENTIDAD_DECLARADA=SI` y rechaza clientes, orígenes y cadenas de
proxy que no sean loopback. Esa barrera evita una exposición accidental durante
una demo, pero no vuelve confiable al encabezado ni autoriza publicar la
aplicación en la red de la bodega.

El servidor comprueba el perfil en cada operación; ocultar una pantalla en el
cliente no es la medida de seguridad. La prueba de permisos tiene además un
control negativo documentado: al retirar temporalmente el guard de Depósito,
la prueba 403 de Campo falla.

Usuarios simulados útiles:

- `1210`, Aciar: perfil depósito.
- `1103`, Funes: perfil depósito.
- `1501`, Molina: perfil campo; recibe HTTP 403 si intenta operar EPP.
- `1601`, Sosa: perfil báscula; recibe HTTP 403 si intenta operar EPP.
- `0988`, Páez: inactivo; no puede iniciar sesión.

## Ejecución local

Backend:

```bash
export SJ_HMAC_DATOS_PERSONALES=desarrollo-local-32-caracteres-minimo
export SJ_CLAVE_CIFRADO_DATOS_PERSONALES=desarrollo-local-32-caracteres-minimo
export SJ_HABILITAR_IDENTIDAD_DECLARADA=SI
PATH="$PWD/.venv/bin:$PATH" npm run api:dev
```

Aplicación móvil web:

```bash
npm run dev:mobile
```

Abrir `http://localhost:3001`. El proxy de desarrollo conecta la app con el
backend en `http://127.0.0.1:8000`. Para un dispositivo se configura
`NEXT_PUBLIC_API_URL` con la dirección alcanzable del backend.

Pruebas específicas:

```bash
.venv/bin/pytest apps/api/tests/rrhh_epp -q
```

## Flujo implementado

1. El operario de depósito declara su legajo en el adaptador local.
2. El backend le asigna `deposito` según puesto y sector.
3. Busca al trabajador por legajo, apellido o DNI.
4. La grilla se arma desde el catálogo RD 068/11 y la matriz Puesto/EPP.
5. El operario selecciona elementos y cantidades; no existe carga libre de
   producto, marca o modelo.
6. El trabajador firma sobre la tablet.
7. Se guarda la entrega, la constancia y el asiento de bitácora.
8. En modo simulado toda pantalla y constancia advierten que no tienen validez
   legal.

El legajo que queda en la bitácora sale de la identidad declarada en el header;
no prueba la identidad real del operario. El API no acepta
`usuario_deposito` enviado en el cuerpo, para evitar una segunda fuente de la
misma declaración.

## Componentes simulados

| Componente | MVP local | Reemplazo previsto |
|---|---|---|
| Legajos | `data/nexus_simulado.yaml` | Vista de solo lectura en Nexus por VPN |
| Catálogo | `data/catalogo_rd068.yaml` | RD 068/11 completo validado por HyS |
| Matriz | `data/matriz_puesto_epp.yaml` | Matriz aprobada por HyS |
| Firma | Trazo o PIN, marcado simulado | `plataforma/firma` |
| Persistencia | SQLite local | PostgreSQL de la suite |
| Identidad | Header local, explícitamente suplantable | Sesión autenticada de `plataforma/identidad` |

El MVP se niega a construir en `produccion` hasta reemplazar autenticación
local, SQLite y firma simulada. Nexus sólo se consulta mediante el repositorio
de legajos; el módulo no expone escritura hacia SQL Server.

El mapa puesto/sector → perfil vive en
`plataforma/parametria/data/perfiles_acceso.yaml`. Su dueño declarado es
Recursos Humanos y su estado es `PROVISORIO`; usa códigos de puesto y sector,
no sus descripciones. Cualquier cambio de asignación se hace allí, no en
`acceso.py`.

## Ubicación en el repositorio

```text
apps/api/src/suite_juviar/modulos/rrhh_epp/
  domain/                 modelos y puertos puros
  application/            consulta de legajo y registro de entrega
  infrastructure/         YAML, Nexus, SQLite y firma simulada
  api/                     API y constancia RD 062/11
  data/                    fuentes provisorias identificadas como simuladas
apps/api/tests/rrhh_epp/   contrato, reglas, permisos y API
apps/mobile/               una app con campo, depósito y báscula
```

La API integrada se publica bajo `/api/v1/rrhh-epp`. El archivo
`sql/vw_legajos_activos.sql` contiene la vista propuesta para Nexus; los nombres
de tablas originales siguen siendo hipótesis que debe confirmar su responsable.

## Pendientes antes de producción

- Catálogo RD 068/11 completo.
- Matriz Puesto/EPP validada por Higiene y Seguridad.
- Códigos reales de puesto y sector para parametrizar el mapa de perfiles.
- VPN, vista y credenciales de solo lectura de Nexus.
- Sustituir la autenticación local por identidad real.
- PostgreSQL para entregas y bitácora inmutable.
- Motor compartido de firma y generación del PDF firmado.
- Operación sin conexión de la app móvil.
- Control de stock del depósito.

Aunque el código pase todas las pruebas, el módulo no puede salir del entorno
de prueba hasta que Higiene y Seguridad valide y firme el catálogo RD 068/11 y
la matriz Puesto/EPP. Después de esa definición de negocio, la próxima mejora
técnica prioritaria es el funcionamiento sin conexión para no perder entregas
en el depósito; el PDF firmado queda después.
