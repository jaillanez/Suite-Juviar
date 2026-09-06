# suite-juviar

Sistema unificado ENAV S.A. — Jubiar. Monolito modular con Domain-Driven Design.

- Base Común vigente: [`Docs/00_Base_Comun_Sistema_Unificado_ENAV_Jubiar_v04.md`](Docs/00_Base_Comun_Sistema_Unificado_ENAV_Jubiar_v04.md)
- Plan de implementación: [`Docs/PLAN_DE_IMPLEMENTACION.md`](Docs/PLAN_DE_IMPLEMENTACION.md)
- Fuente inicial de RRHH/EPP: [`Docs/README_rrhh_epp.md`](Docs/README_rrhh_epp.md)
- Estado real y bloqueos: [`Docs/ESTADO_INSTRUCCIONES_AGENTE.md`](Docs/ESTADO_INSTRUCCIONES_AGENTE.md)
- Arquitectura y decisiones: [`Docs/ARQUITECTURA.md`](Docs/ARQUITECTURA.md)
- Decisiones registradas: [`Docs/adr/`](Docs/adr/)
- README operativo vigente de EPP: [`apps/api/src/suite_juviar/modulos/rrhh_epp/README.md`](apps/api/src/suite_juviar/modulos/rrhh_epp/README.md)

```
apps/
  api/        backend único desplegable (FastAPI)
  consulta/   bot de consulta externa — deployable aparte, DMZ, solo lectura
  web/        sitio público aislado (Next.js 16)
  mobile/     app única con tres perfiles (Capacitor 8.5.1)
packages/
  contratos/  tipos generados desde el OpenAPI de la API
  ui/         componentes shadcn/ui compartidos
sql/          roles, inmutabilidad de bitácora, patrón de datos personales
```

## Desarrollo local

Requisitos: Node.js 22, pnpm 10.15 y Python 3.14.

```bash
cp .env.example .env
pnpm install
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -e "apps/api[dev]" -e apps/consulta

pnpm build
.venv/bin/pytest apps/api
cd apps/api && ../../.venv/bin/lint-imports
```

Para ejecutar los servicios:

```bash
pnpm dev:web
pnpm dev:mobile
pnpm api:dev
```

Las claves incluidas en `.env.example` son solo marcadores de desarrollo y deben
reemplazarse por secretos administrados antes de cualquier despliegue.
