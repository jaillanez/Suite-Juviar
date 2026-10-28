-- DMZ: fila de camiones, turnos y configuración operativa.
CREATE SCHEMA IF NOT EXISTS fila;
ALTER TABLE consulta.descarga_publica ADD COLUMN IF NOT EXISTS id_suite bigint;
CREATE UNIQUE INDEX IF NOT EXISTS ux_descarga_publica_id_suite
    ON consulta.descarga_publica(id_suite) WHERE id_suite IS NOT NULL;

CREATE TABLE IF NOT EXISTS fila.capacidad (
    sede text NOT NULL,
    fecha date,
    kg_dia bigint NOT NULL CHECK (kg_dia >= 0),
    actualizado_por text NOT NULL,
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (sede, fecha)
);
CREATE TABLE IF NOT EXISTS fila.productor_organico (
    clientecuit text PRIMARY KEY,
    certificadora text NOT NULL,
    vence date,
    cargado_por text NOT NULL,
    cargado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fila.turno (
    id bigserial PRIMARY KEY,
    sede text NOT NULL,
    fecha date NOT NULL,
    clientecuit text NOT NULL,
    clientecodigo text,
    camiones integer NOT NULL CHECK (camiones BETWEEN 1 AND 50),
    camiones_usados integer NOT NULL DEFAULT 0 CHECK (camiones_usados >= 0),
    kg_por_camion integer NOT NULL CHECK (kg_por_camion BETWEEN 1000 AND 40000),
    declara_organica boolean NOT NULL DEFAULT false,
    estado text NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','cancelado')),
    pedido_por text NOT NULL,
    canal text NOT NULL CHECK (canal IN ('whatsapp','web','bodega')),
    creado_en timestamptz NOT NULL DEFAULT now(),
    CHECK (camiones_usados <= camiones)
);
CREATE INDEX IF NOT EXISTS ix_turno_dia ON fila.turno (sede, fecha) WHERE estado='activo';
CREATE INDEX IF NOT EXISTS ix_turno_cuit ON fila.turno (clientecuit, fecha);

CREATE TABLE IF NOT EXISTS fila.vehiculo (
    patente text PRIMARY KEY,
    patente_acoplado text,
    ultimo_chofer_dni text,
    ultimo_chofer_nombre text,
    ultimo_chofer_tel text,
    ultimo_clientecuit text,
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fila.viaje (
    id bigserial PRIMARY KEY,
    id_cliente uuid NOT NULL UNIQUE,
    ticket text NOT NULL UNIQUE CHECK (length(ticket) >= 43),
    fecha_operativa date,
    numero_dia integer,
    productor_texto text,
    sede text NOT NULL,
    patente text NOT NULL,
    patente_acoplado text,
    chofer_dni text,
    chofer_nombre text,
    chofer_tel text,
    clientecuit text,
    clientecodigo text,
    declara_organica boolean NOT NULL DEFAULT false,
    turno_id bigint REFERENCES fila.turno(id),
    origen text NOT NULL CHECK (origen IN ('qr','guardia')),
    estado text NOT NULL CHECK (estado IN (
        'pendiente','en_espera','llamado','en_bascula','descargado','cancelado'
    )),
    registrado_en timestamptz NOT NULL DEFAULT now(),
    confirmado_en timestamptz,
    confirmado_por text,
    llamado_en timestamptz,
    llamado_por text,
    en_bascula_en timestamptz,
    descarga_id bigint,
    cerrado_en timestamptz,
    motivo_cierre text,
    CHECK (estado IN ('pendiente','cancelado') OR
           (confirmado_en IS NOT NULL AND clientecuit IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_viaje_numero_dia
    ON fila.viaje (sede, fecha_operativa, numero_dia) WHERE numero_dia IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_viaje_patente_activa
    ON fila.viaje (sede, patente)
    WHERE estado IN ('pendiente','en_espera','llamado','en_bascula');
CREATE INDEX IF NOT EXISTS ix_viaje_espera ON fila.viaje(sede, estado, confirmado_en);

CREATE TABLE IF NOT EXISTS fila.evento (
    id bigserial PRIMARY KEY,
    id_cliente uuid UNIQUE,
    viaje_id bigint REFERENCES fila.viaje(id),
    turno_id bigint REFERENCES fila.turno(id),
    tipo text NOT NULL,
    actor text NOT NULL,
    motivo text,
    detalle jsonb,
    momento_cliente timestamptz,
    momento timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_evento_viaje ON fila.evento(viaje_id, momento);

DO $$ BEGIN CREATE ROLE fila_publico LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE fila_guardia LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE fila_turnos LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE fila_worker LOGIN;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

REVOKE ALL ON SCHEMA fila FROM PUBLIC, fila_publico, fila_guardia, fila_turnos, fila_worker;
REVOKE ALL ON ALL TABLES IN SCHEMA fila FROM PUBLIC, fila_publico,
    fila_guardia, fila_turnos, fila_worker;
GRANT USAGE ON SCHEMA fila TO fila_publico, fila_guardia, fila_turnos, fila_worker;
GRANT SELECT, INSERT, UPDATE ON fila.viaje, fila.turno, fila.vehiculo, fila.evento
    TO fila_guardia;
GRANT SELECT ON fila.productor_organico, fila.capacidad TO fila_guardia;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fila TO fila_guardia;
GRANT SELECT, INSERT, UPDATE ON fila.turno TO fila_turnos;
GRANT SELECT ON fila.capacidad, fila.productor_organico TO fila_turnos;
GRANT USAGE, SELECT ON SEQUENCE fila.turno_id_seq TO fila_turnos;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA fila TO fila_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fila TO fila_worker;

CREATE OR REPLACE FUNCTION fila.registrar_llegada(
    p_id_cliente uuid, p_ticket text, p_productor text, p_sede text,
    p_patente text, p_telefono text, p_ip text
) RETURNS TABLE(id bigint, ticket text, estado text, patente text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
DECLARE v_id bigint;
BEGIN
    IF (SELECT count(*) FROM fila.evento WHERE tipo='registro_publico'
        AND detalle->>'ip'=p_ip AND momento > now()-interval '1 hour') >= 5 THEN
        RAISE EXCEPTION 'limite_registros' USING ERRCODE='P0001';
    END IF;
    INSERT INTO fila.viaje
        (id_cliente,ticket,productor_texto,sede,patente,chofer_tel,origen,estado)
    VALUES (p_id_cliente,p_ticket,p_productor,p_sede,p_patente,p_telefono,'qr','pendiente')
    ON CONFLICT (id_cliente) DO UPDATE SET id_cliente=EXCLUDED.id_cliente
    RETURNING fila.viaje.id INTO v_id;
    INSERT INTO fila.evento(id_cliente,viaje_id,tipo,actor,detalle)
    VALUES (p_id_cliente,v_id,'registro_publico',
            'chofer:'||COALESCE(p_telefono,'sin-telefono'),jsonb_build_object('ip',p_ip))
    ON CONFLICT (id_cliente) DO NOTHING;
    RETURN QUERY SELECT v.id,v.ticket,v.estado,v.patente FROM fila.viaje v WHERE v.id=v_id;
END $$;

CREATE OR REPLACE FUNCTION fila.leer_ticket(p_ticket text)
RETURNS TABLE(id bigint,sede text,patente text,estado text,numero_dia integer,
              confirmado_en timestamptz,posicion integer,adelante integer)
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT v.id,v.sede,v.patente,v.estado,v.numero_dia,v.confirmado_en,
           CASE WHEN v.estado='en_espera' THEN 1 + (
               SELECT count(*)::integer FROM fila.viaje o
               WHERE o.sede=v.sede AND o.estado='en_espera' AND
                 (CASE WHEN o.declara_organica AND EXISTS (
                       SELECT 1 FROM fila.productor_organico p
                       WHERE p.clientecuit=o.clientecuit
                         AND (p.vence IS NULL OR p.vence>=current_date)) THEN 1
                       WHEN o.turno_id IS NOT NULL THEN 2 ELSE 3 END,
                  o.confirmado_en,o.id)
                 <
                 (CASE WHEN v.declara_organica AND EXISTS (
                       SELECT 1 FROM fila.productor_organico p
                       WHERE p.clientecuit=v.clientecuit
                         AND (p.vence IS NULL OR p.vence>=current_date)) THEN 1
                       WHEN v.turno_id IS NOT NULL THEN 2 ELSE 3 END,
                  v.confirmado_en,v.id)) ELSE NULL END,
           CASE WHEN v.estado='en_espera' THEN (
               SELECT count(*)::integer FROM fila.viaje o
               WHERE o.sede=v.sede AND o.estado='en_espera' AND o.id<>v.id AND
                 (CASE WHEN o.declara_organica AND EXISTS (
                       SELECT 1 FROM fila.productor_organico p
                       WHERE p.clientecuit=o.clientecuit
                         AND (p.vence IS NULL OR p.vence>=current_date)) THEN 1
                       WHEN o.turno_id IS NOT NULL THEN 2 ELSE 3 END,
                  o.confirmado_en,o.id)
                 <
                 (CASE WHEN v.declara_organica AND EXISTS (
                       SELECT 1 FROM fila.productor_organico p
                       WHERE p.clientecuit=v.clientecuit
                         AND (p.vence IS NULL OR p.vence>=current_date)) THEN 1
                       WHEN v.turno_id IS NOT NULL THEN 2 ELSE 3 END,
                  v.confirmado_en,v.id)) ELSE NULL END
    FROM fila.viaje v WHERE v.ticket=p_ticket
$$;

CREATE OR REPLACE FUNCTION fila.autocompletar_patente(p_patente text)
RETURNS TABLE(chofer text, productor text)
LANGUAGE sql SECURITY DEFINER SET search_path = fila, pg_temp AS $$
    SELECT CASE WHEN v.ultimo_chofer_nombre IS NULL THEN ''
                ELSE split_part(v.ultimo_chofer_nombre,' ',1)||' '
                     ||left(split_part(v.ultimo_chofer_nombre,' ',2),1)||'.' END,
           CASE WHEN v.ultimo_clientecuit IS NULL THEN '' ELSE 'Productor conocido' END
    FROM fila.vehiculo v WHERE v.patente=p_patente
$$;

REVOKE ALL ON FUNCTION fila.registrar_llegada(uuid,text,text,text,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION fila.leer_ticket(text), fila.autocompletar_patente(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila.registrar_llegada(uuid,text,text,text,text,text,text),
    fila.leer_ticket(text), fila.autocompletar_patente(text) TO fila_publico;
