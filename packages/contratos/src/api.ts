/**
 * Contrato inicial. Se reemplaza con `pnpm --filter @suite-juviar/contratos generar`
 * cuando la API está disponible.
 */
export interface paths {
  "/salud": {
    get: {
      responses: {
        200: {
          content: { "application/json": { estado: string } };
        };
      };
    };
  };
}
