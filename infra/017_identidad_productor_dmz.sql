-- Base DMZ: proyecta la identidad CLIENTECUIT usada por el bot.
ALTER TABLE consulta.descarga_publica
    ADD COLUMN IF NOT EXISTS clientecuit text;
CREATE INDEX IF NOT EXISTS ix_publica_clientecuit
    ON consulta.descarga_publica (clientecuit, fecha DESC);

ALTER TABLE consulta.telefono_productor
    RENAME COLUMN nroinscripto TO clientecuit;
ALTER TABLE consulta.telefono_productor
    DROP CONSTRAINT IF EXISTS telefono_productor_pkey;
ALTER TABLE consulta.telefono_productor
    ADD PRIMARY KEY (telefono, clientecuit);

ALTER TABLE consulta.bitacora_consulta
    RENAME COLUMN nroinscripto TO clientecuit;

