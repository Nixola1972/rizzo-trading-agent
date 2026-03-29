-- ============================================
-- MES/MRP/WMS Sistema Integrato
-- Migration 002: Dati iniziali (Seed)
-- ============================================

-- Magazzini
INSERT INTO warehouses (id, name, location, country) VALUES
    ('MAG-IT',      'Magazzino Italia',     'Bagnatica (BG)',   'IT'),
    ('MAG-AL',      'Magazzino Albania',    'Tirana',           'AL'),
    ('MAG-TRANSIT', 'In Transito',          'IT ↔ AL',          NULL),
    ('MAG-CL',      'Conto Lavoro',         'Terzisti',         NULL);

-- Zone Magazzino Italia
INSERT INTO warehouse_zones (id, warehouse_id, name, zone_type) VALUES
    ('IT-INCOMING',   'MAG-IT', 'Ricevimento Italia',           'INCOMING'),
    ('IT-QC',         'MAG-IT', 'Controllo Qualità Italia',     'QC'),
    ('IT-STOCK',      'MAG-IT', 'Stock Disponibile Italia',     'STOCK'),
    ('IT-RESERVED',   'MAG-IT', 'Riservato per Ordini',         'RESERVED'),
    ('IT-STAGING',    'MAG-IT', 'Pronto per Spedizione AL',     'STAGING'),
    ('IT-QUARANTINE', 'MAG-IT', 'Non Conforme / Quarantena',    'QUARANTINE');

-- Zone Magazzino Albania
INSERT INTO warehouse_zones (id, warehouse_id, name, zone_type) VALUES
    ('AL-INCOMING',   'MAG-AL', 'Ricevuto Albania',             'INCOMING'),
    ('AL-STOCK',      'MAG-AL', 'Stock Disponibile Albania',    'STOCK'),
    ('AL-WIP',        'MAG-AL', 'In Lavorazione (WIP)',         'WIP'),
    ('AL-FG',         'MAG-AL', 'Prodotto Finito Albania',      'FG'),
    ('AL-RETURN',     'MAG-AL', 'Preparazione Rientro IT',      'STAGING');

-- Zone Transito
INSERT INTO warehouse_zones (id, warehouse_id, name, zone_type) VALUES
    ('TR-TRANSIT',    'MAG-TRANSIT', 'In Transito IT↔AL',       'STOCK');

-- Sequenze iniziali per codifica
INSERT INTO code_sequences (category, subcategory, last_sequence) VALUES
    ('RES', '0201', 0), ('RES', '0402', 0), ('RES', '0603', 0), ('RES', '0805', 0), ('RES', '1206', 0),
    ('CAP', '0201', 0), ('CAP', '0402', 0), ('CAP', '0603', 0), ('CAP', '0805', 0), ('CAP', '1206', 0),
    ('CAP', 'ELEC', 0),
    ('IC',  'QFP', 0),  ('IC',  'QFN', 0),  ('IC',  'BGA', 0),  ('IC',  'SOP', 0), ('IC', 'DIP', 0),
    ('DIO', 'SMD', 0),  ('DIO', 'THT', 0),
    ('TRA', 'SMD', 0),  ('TRA', 'THT', 0),
    ('CON', 'USB', 0),  ('CON', 'HDR', 0),  ('CON', 'FPC', 0),  ('CON', 'RJ45', 0), ('CON', 'JACK', 0),
    ('IND', 'SMD', 0),  ('IND', 'THT', 0),
    ('CRI', 'SMD', 0),  ('CRI', 'THT', 0),
    ('PCB', '2L', 0),   ('PCB', '4L', 0),   ('PCB', '6L', 0),
    ('MEC', 'VIT', 0),  ('MEC', 'DIST', 0), ('MEC', 'STAF', 0),
    ('ETI', 'STD', 0),
    ('IMB', 'BOX', 0),  ('IMB', 'BUSTA', 0),
    ('ALT', 'GEN', 0);
