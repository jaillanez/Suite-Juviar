/**
 * Tipos compartidos entre web y mobile. Se generan desde el OpenAPI de la API
 * (`pnpm --filter @suite-juviar/contratos generar`), no se escriben a mano: un
 * tipo escrito a mano se desincroniza del backend sin que nadie se entere.
 */
export * from "./api";
