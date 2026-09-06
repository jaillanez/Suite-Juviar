# Selección de personal

El postulante vive en el registro común de Terceros con tipo `POSTULANTE`; no es
empleado y no se crea una cuarta lista de personas. Su clave es el DNI cuando
existe y, mientras no exista, el correo. El dueño del dato es RRHH. Si ingresa,
el registro se conserva y se vincula al legajo creado externamente en Nexus.

## Funcionalidad incorporada

- Tipo `POSTULANTE`, identidad canónica por DNI o correo y vínculo posterior al
  legajo de Nexus sin convertir ni borrar el registro de selección.
- Ingesta idempotente desde carpeta configurable y correo local simulado; conserva
  los bytes originales, su referencia de origen y SHA-256 sin mover el archivo fuente.
- Extracción explicable de edad/fecha, estudios, experiencia, oficio, localidad y
  contacto: cada valor nace `NO_VERIFICADO` con su fragmento; lo faltante va a revisión.
- Filtros y ranking explicables por edad, secundaria y perfil; cada búsqueda conserva
  quién definió el criterio y cuándo, y una coincidencia abierta genera un aviso simulado.

> El filtro por edad es una decisión de la empresa, no del sistema. El asesor legal
> debe revisarlo antes de usarlo en una búsqueda real.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Persistencia protegida del postulante | PENDIENTE | Crear el repositorio PostgreSQL usando HMAC + AES-GCM para DNI y correo. |
| Política de retención de CV | PENDIENTE | RRHH y asesor legal deben definir plazo, acceso y tratamiento de datos personales. |
| Ruta de la carpeta de Chimbas | PENDIENTE | Infraestructura debe informar y habilitar la ruta real de solo lectura. |
| Acceso a la bandeja de correo | SIMULADO | Reemplazar la bandeja local por un adaptador autenticado cuando RRHH entregue cuenta y credenciales. |
| Persistencia durable de originales | PENDIENTE | Conectar el puerto a almacenamiento cifrado e inmutable; hoy sólo existe el adaptador en memoria para pruebas. |
| Reglas de extracción | SIMULADO | Validar con CV reales de RRHH y sustituir o ajustar las expresiones provisorias; nunca auto-verifican ni descartan. |
| PDF escaneado sin texto | PENDIENTE | Incorporar OCR cuando RRHH confirme el volumen; mientras tanto va completo a revisión. |
| Palabras clave por perfil | PROPUESTA_SIN_VALIDAR | RRHH debe validar el YAML antes de usarlo para una búsqueda real. |
| Canal proactivo a RRHH | SIMULADO | Conectar el notificador al canal corporativo; hoy sólo se prueba en memoria. |

