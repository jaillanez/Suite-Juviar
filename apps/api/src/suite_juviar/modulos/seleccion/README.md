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
- Originales y extracciones tienen adaptador PostgreSQL: PDF, nombre, referencia,
  valores y fragmentos se guardan cifrados; la búsqueda técnica usa HMAC.
- El rol PostgreSQL `suite_seleccion_rrhh` puede operar únicamente este esquema;
  el control de §6.5 demuestra en la base local que no lee EPP ni Capacitación.

> El filtro por edad es una decisión de la empresa, no del sistema. El asesor legal
> debe revisarlo antes de usarlo en una búsqueda real.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Persistencia protegida del postulante | PENDIENTE | El CV y su extracción ya están cifrados; falta el repositorio PostgreSQL del registro Terceros para DNI y correo. |
| Política de retención de CV | PENDIENTE | RRHH y asesor legal deben definir plazo, acceso y tratamiento de datos personales. |
| Ruta de la carpeta de Chimbas | NO BLOQUEA CALIBRACIÓN | La integración definitiva sigue pendiente; para calibrar alcanza una muestra segura de 20 a 30 CV enviada por RRHH. |
| Muestra de calibración | PENDIENTE DICIEMBRE 2026 | RRHH debe enviar 20 a 30 CV con tratamiento autorizado antes de diciembre; no hace falta esperar la ruta de Chimbas. |
| Acceso a la bandeja de correo | SIMULADO | Reemplazar la bandeja local por un adaptador autenticado cuando RRHH entregue cuenta y credenciales. |
| Rotación y custodia de claves | PENDIENTE | Definir KMS/secret manager y procedimiento de rotación antes de datos reales. |
| Reglas de extracción | SIMULADO | Validar con CV reales de RRHH y sustituir o ajustar las expresiones provisorias; nunca auto-verifican ni descartan. |
| PDF escaneado sin texto | PENDIENTE | Incorporar OCR cuando RRHH confirme el volumen; mientras tanto va completo a revisión. |
| Palabras clave por perfil | PROPUESTA_SIN_VALIDAR | RRHH debe validar el YAML antes de usarlo para una búsqueda real. |
| Canal proactivo a RRHH | SIMULADO | Conectar el notificador al canal corporativo; hoy sólo se prueba en memoria. |
