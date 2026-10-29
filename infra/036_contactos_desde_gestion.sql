-- SUITE: Gestión administra los contactos de productores con el rol terceros_gestor.
--
-- El historial (terceros.contacto_evento) no aceptaba las altas manuales que registra
-- Gestión ('alta' y 'alta_reactivada'): se suman a la lista de tipos permitidos.
-- La clave de terceros_gestor NO va en este archivo; se fija al aplicar:
--   ALTER ROLE terceros_gestor PASSWORD '...';
-- Se aplica antes de instalar el código. Idempotente.

ALTER TABLE terceros.contacto_evento DROP CONSTRAINT IF EXISTS contacto_evento_tipo_check;
ALTER TABLE terceros.contacto_evento ADD CONSTRAINT contacto_evento_tipo_check CHECK (tipo IN (
    'importacion_bodega', 'invitado', 'validado', 'intento_fallido', 'invitacion_anulada',
    'permisos_cambiados', 'baja', 'reemplazo_administrador', 'alta', 'alta_reactivada'
));
