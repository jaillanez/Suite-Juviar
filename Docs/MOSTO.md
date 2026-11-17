# Mosto sulfitado y virgen

Sección **Producción → Mosto** de Gestión (módulo `apps/api/src/suite_juviar/modulos/mosto`).
Los datos viven en la base local de módulos de Gestión; la única pieza en la base de la fila
es la cola de WhatsApp (`infra/040_aviso_interno_mosto.sql`).

## Quién hace qué

| Perfil | Puede |
|---|---|
| Comercial (`COMERCIAL`) | Cargar compras, decidir por escasez sobre ofertas rechazadas, liquidar sin margen (excepción), cerrar y liquidar |
| Compras (`COMPRAS`) | Cargar compras |
| Laboratorio (`LABORATORIO`) | Análisis de la oferta, decisión de Calidad, muestras por pileta, análisis de cada viaje |
| Jefatura de Producción (`PRODUCCION`) | Aprobar para mezcla lo que rechazó Calidad (o confirmar el rechazo), registrar descarga y pases en planta |
| Báscula (`BASCULA`) | Ingresar camiones de mosto contra una compra aprobada |
| Superadministrador | Todo, más los parámetros |

## Recorrido de una compra

1. Comercial o Compras la carga: proveedor, CUIT, tipo, litros y precio base por litro.
2. Laboratorio carga el análisis de la muestra (azúcar g/L, absorbancia 520 nm, alcohol) y Calidad aprueba o rechaza.
3. Si Calidad rechaza, el Jefe de Producción puede aprobarla para mezcla. Sobre una oferta rechazada, Comercial puede decidir por escasez de mercado.
4. Aprobada: Laboratorio ratifica pileta por pileta y Báscula ingresa los camiones.
5. Cada viaje lleva su análisis y su descarga (y los pases siguientes: pileta, tanque, concentrador).
6. Comercial cierra: se promedia el azúcar de todos los viajes, ponderado por litros, y queda fijo el precio sugerido.

Precio por litro = precio base × (azúcar liquidada / azúcar de referencia), donde azúcar
liquidada = promedio − margen, salvo excepción comercial.

## Parámetros (Gestión → Parámetros → Mosto)

- Azúcar de referencia del precio base (220 g/L).
- Margen de resguardo (1 g/L).
- Horas límite del mosto virgen sin descargar. Sin cargar, no hay alarma.
- A quién avisar: nombre, mail y celular.

## Alarma de mosto virgen

Cada minuto la API revisa los camiones de mosto virgen sin descarga. Al pasar las horas
límite se avisa una sola vez por camión: queda el aviso en rojo en la sección Mosto hasta que
se descarga, y sale a cada persona cargada por mail y por WhatsApp.

- Mail: usa `SJ_SMTP_HOST`, `SJ_SMTP_PUERTO`, `SJ_SMTP_REMITENTE`, `SJ_SMTP_USUARIO`,
  `SJ_SMTP_CLAVE` y `SJ_SMTP_TLS`. Sin configurar, el aviso dice «canal sin configurar».
- WhatsApp: `fila.encolar_aviso_mosto` recibe los datos del camión, arma el texto en la base y
  lo deja en `fila.aviso_productor`; lo manda el worker del bot. Sólo acepta celulares activos
  en «Personal en el bot» y hasta 60 avisos internos por hora. Sale de verdad cuando el bot
  tenga las credenciales de Chattigo.
- La sección Mosto muestra a quién se avisó por nombre, sin mails ni celulares; el error
  técnico de un canal queda sólo en el registro del servidor.
- `SJ_ALARMA_MOSTO=0` apaga el ciclo (pruebas).
