# Gestión en un solo contenedor: las pantallas compiladas y la API que las sirve.
# Se construye desde la raíz del repositorio:
#   docker build -f infra/gestion/Dockerfile --build-arg COMMIT=<sha> -t suite-juviar-gestion:<sha> .

FROM node:22-alpine AS pantallas
WORKDIR /repo
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages ./packages
COPY apps/gestion ./apps/gestion
COPY apps/web/package.json ./apps/web/package.json
COPY apps/mobile/package.json ./apps/mobile/package.json
RUN pnpm install --frozen-lockfile --filter "@suite-juviar/gestion..."
ARG COMMIT=local
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_GIT_COMMIT=$COMMIT \
    NEXT_PUBLIC_OCULTAR_MARCAS_PRUEBA=1
RUN pnpm --filter @suite-juviar/gestion build:static

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml /opt/gestion/api/pyproject.toml
COPY apps/api/src /opt/gestion/api/src
RUN pip install /opt/gestion/api "httpx>=0.28" && rm -rf /opt/gestion/api
COPY --from=pantallas /repo/apps/gestion/out /opt/gestion/pantallas
# Datos de ejemplo para un servidor nuevo: docker exec suite-juviar-gestion python /opt/gestion/cargar_demostracion.py
COPY apps/api/tools/cargar_demostracion.py /opt/gestion/cargar_demostracion.py
RUN useradd --system --uid 10001 --home-dir /datos gestion
USER gestion
WORKDIR /datos
ENV SJ_GESTION_ESTATICOS=/opt/gestion/pantallas \
    SJ_IDENTIDAD_REAL=1 \
    SJ_OCULTAR_MARCAS_PRUEBA=1 \
    SJ_USUARIOS_SQLITE_PATH=/datos/usuarios.sqlite3 \
    SJ_MODULOS_SQLITE_PATH=/datos/modulos.sqlite3 \
    SJ_RRHH_EPP_SQLITE_PATH=/datos/rrhh_epp.sqlite3 \
    SJ_RECEPCION_SQLITE_PATH=/datos/recepcion.sqlite3
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ingreso/estado',timeout=4)"
# La dirección real de quien entra solo se toma de las cabeceras que manda Caddy: la red
# en la que se confía va en FORWARDED_ALLOW_IPS (/etc/suite/gestion.env). Sin esa
# variable no se confía en nadie y todos los pedidos parecen venir de Caddy.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "suite_juviar.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
