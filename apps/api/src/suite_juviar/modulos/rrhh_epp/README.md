# RRHH / EPP

Módulo único de entrega de ropa de trabajo y elementos de protección personal.
Funciona en entorno de prueba con legajos simulados, catálogo RD 068/11 real,
matriz `PROPUESTA_SIN_VALIDAR`, firma simulada y PostgreSQL local. SQLite queda
limitado al aislamiento de las pruebas automatizadas.

## Funcionalidad incorporada

- Catálogo normativo de 145 elementos y matriz compuesta por base, sector y puesto.
- Perfiles operativos resueltos por Parametría, sin perfil permisivo por defecto.
- Vida útil `REFERENCIAL_INVESTIGADO` y auditoría no bloqueante del catálogo.
- Catálogo de dos niveles: la matriz usa el elemento normativo y la entrega guarda
  código interno, marca, modelo, talle y color del ítem elegido.
- Cola offline en la tablet: guarda antes de enviar, muestra pendientes, reintenta con
  espera exponencial y no ofrece constancia hasta la confirmación idempotente del servidor.
- Constancia PDF individual: un trabajador por archivo, original inmutable conservado con
  SHA-256 y marca visible `SIN VALIDEZ LEGAL` mientras la firma sea simulada.
- Las reposiciones crean una versión nueva de la constancia vigente, agregan los renglones
  anteriores y declaran qué versión reemplazan sin modificar los bytes históricos.
- Dos circuitos: planificación estacional programada por sector y reposición espontánea
  por rotura o desgaste; ambos quedan identificados en entrega, bitácora y constancia.
- Stock por ítem: cada entrega confirmada descuenta existencias y al alcanzar el mínimo
  genera automáticamente un aviso pendiente para Compras. El stock inicial es simulado
  y su dueño declarado es Depósito.
- Persistencia PostgreSQL para entregas, constancias originales, stock, avisos y bitácora;
  el adaptador de Nexus permanece separado y de solo lectura.

## Deuda técnica y datos pendientes

| Deuda o dato | Estado | Para resolverla |
|---|---|---|
| Transacción única entrega-stock-bitácora | PENDIENTE | Unificar las tres escrituras en una unidad de trabajo PostgreSQL antes de la prueba con varias tablets. |
| Protección criptográfica de DNI y legajo en RRHH/EPP | PENDIENTE | Aplicar HMAC + AES-GCM de `plataforma/cripto` antes de cargar datos reales. |
| Umbral offline de 20 entregas o 24 horas | PROPUESTA_SIN_VALIDAR | Confirmación de Operaciones y de Higiene y Seguridad. |
| Identidad real del operario | PENDIENTE | Integrar `plataforma/identidad`; el header local es suplantable. |
| Firma digital del PDF por la empresa | PENDIENTE | Certificado y motor real de `plataforma/firma`; el PDF actual sólo se imprime y firma en papel. |
| Volumen diario de temporada alta | PENDIENTE | Observación presencial en depósito; la pantalla se diseñó como lista masiva mientras falta el dato. |
| Ítems reales de marcas, modelos, talles y colores | SIMULADO | Reemplazar los 435 registros `SIM-*` cuando llegue el Excel maestro de Higiene y Seguridad. |
| Existencias y mínimos reales por ítem | SIMULADO | Depósito debe sustituir las cantidades ficticias y aprobar cada mínimo antes del uso real. |
| Envío del aviso de mínimo a Compras | PENDIENTE | Conectar los avisos durables al outbox/notificador corporativo; hoy quedan disponibles en la API. |
