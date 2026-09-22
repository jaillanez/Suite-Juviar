-- DMZ: proyección mínima de tareas que usa el bot y la web de turnos.
ALTER TABLE consulta.telefono_productor
    ADD COLUMN IF NOT EXISTS tareas text[] NOT NULL DEFAULT '{ver_informes}';
ALTER TABLE consulta.telefono_productor DROP CONSTRAINT IF EXISTS ck_telefono_tareas;
ALTER TABLE consulta.telefono_productor ADD CONSTRAINT ck_telefono_tareas CHECK (
    cardinality(tareas) > 0
    AND tareas <@ ARRAY['ver_informes','pedir_turnos','administrar_contactos']
);
