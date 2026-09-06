# Selección de personal

El postulante vive en el registro común de Terceros con tipo `POSTULANTE`; no es
empleado y no se crea una cuarta lista de personas. Su clave es el DNI cuando
existe y, mientras no exista, el correo. El dueño del dato es RRHH. Si ingresa,
el registro se conserva y se vincula al legajo creado externamente en Nexus.

## Funcionalidad incorporada

- Tipo `POSTULANTE`, identidad canónica por DNI o correo y vínculo posterior al
  legajo de Nexus sin convertir ni borrar el registro de selección.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Persistencia protegida del postulante | PENDIENTE | Crear el repositorio PostgreSQL usando HMAC + AES-GCM para DNI y correo. |
| Política de retención de CV | PENDIENTE | RRHH y asesor legal deben definir plazo, acceso y tratamiento de datos personales. |

