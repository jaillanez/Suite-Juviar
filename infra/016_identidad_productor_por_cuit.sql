-- Corrige la identidad del productor: NROINSCRIPTO identifica la bodega,
-- mientras que CLIENTECUIT identifica al titular que consulta sus descargas.

ALTER TABLE terceros.contacto_whatsapp
    RENAME COLUMN nroinscripto TO clientecuit;
ALTER TABLE terceros.contacto_whatsapp
    DROP CONSTRAINT IF EXISTS contacto_whatsapp_pkey;
ALTER TABLE terceros.contacto_whatsapp
    ADD PRIMARY KEY (telefono, clientecuit);

