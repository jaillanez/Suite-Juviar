-- Emula en local la réplica de parametría que realiza el worker interno.
-- Los valores son los definidos por plataforma/parametria.
INSERT INTO web.catalogo (tipo, codigo, nombre_es, nombre_en, orden)
VALUES
    ('linea_producto', 'bulk_wine', 'Vino a granel', 'Bulk wine', 10),
    ('linea_producto', 'jcu_standard', 'Mosto estándar', 'Standard concentrate', 20),
    ('linea_producto', 'jcu_decolourised', 'Mosto descolorido', 'De-colored', 30),
    ('linea_producto', 'jcu_virgin', 'Mosto virgen (sin SO₂)', 'Virgin (no SO₂)', 40),
    ('linea_producto', 'jcu_alcoholised', 'Alcoholizado', 'Alcohol added', 50),
    ('formato_despacho', 'Flexitank_4650_gal', 'Flexitank 4.650 gal', 'Flexitank 4,650 gal', 10),
    ('formato_despacho', 'Flexitank_4200_gal', 'Flexitank 4.200 gal', 'Flexitank 4,200 gal', 20),
    ('formato_despacho', 'Wooden_bin_1560_kg', 'Bin de madera 1.560 kg', 'Wooden bin 1,560 kg', 30),
    ('formato_despacho', 'Drum_60_gal', 'Tambor 60 gal', 'Drum 60 gal', 40),
    ('certificacion', 'FSSC_22000', 'FSSC 22000', 'FSSC 22000', 10),
    ('certificacion', 'Organic_Letis', 'Orgánico (Letis)', 'Organic (Letis)', 20),
    ('certificacion', 'Kosher', 'Kosher', 'Kosher', 30),
    ('certificacion', 'Halal', 'Halal', 'Halal', 40),
    ('certificacion', 'Vegan', 'Vegano', 'Vegan', 50),
    ('certificacion', 'BDA_Sustainability', 'BDA Sustentabilidad', 'BDA Sustainability', 60),
    ('certificacion', 'SMETA_4P', 'SMETA 4-Pillars', 'SMETA 4-Pillars', 70),
    ('certificacion', 'Sellos_Argentinos', 'Sellos Argentinos', 'Sellos Argentinos', 80)
ON CONFLICT (tipo, codigo) DO UPDATE
SET nombre_es = EXCLUDED.nombre_es,
    nombre_en = EXCLUDED.nombre_en,
    orden = EXCLUDED.orden,
    vigente = true;
