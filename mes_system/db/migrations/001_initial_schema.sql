-- ============================================
-- MES/MRP/WMS Sistema Integrato
-- Trade Skill S.R.L. / ItalJobs
-- Migration 001: Schema Iniziale
-- ============================================

-- Estensioni necessarie
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- SCHEMA: ANAGRAFICA COMPONENTI
-- ============================================

CREATE TABLE components (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internal_code   VARCHAR(30) UNIQUE NOT NULL,  -- TS-RES-0805-000001
    mpn             VARCHAR(100),
    manufacturer    VARCHAR(100),
    description     VARCHAR(500),
    category        VARCHAR(10) NOT NULL,          -- RES, CAP, IC...
    subcategory     VARCHAR(20),
    package         VARCHAR(30),
    datasheet_url   TEXT,
    -- Dati logistici/doganali
    net_weight_g    DECIMAL(10,4),
    gross_weight_g  DECIMAL(10,4),
    units_per_pkg   INTEGER,
    taric_code      VARCHAR(20),
    country_origin  VARCHAR(3),                    -- ISO 3166
    customs_value   DECIMAL(10,4),
    -- Dati tecnici
    nominal_value   VARCHAR(50),
    tolerance       VARCHAR(20),
    voltage_rating  VARCHAR(20),
    rohs_compliant  BOOLEAN DEFAULT TRUE,
    msl_level       SMALLINT,
    temp_range      VARCHAR(30),
    -- Dati commerciali
    moq             INTEGER DEFAULT 1,
    order_multiple  INTEGER DEFAULT 1,
    lead_time_days  INTEGER,
    -- Dati qualità
    inspection_level VARCHAR(20) DEFAULT 'SAMPLING', -- SKIP, SAMPLING, FULL
    acceptance_criteria TEXT,
    inspection_instructions TEXT,
    -- Sync Danea
    danea_code      VARCHAR(50),
    -- Audit
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      VARCHAR(50)
);

CREATE TABLE component_suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    supplier_name   VARCHAR(200) NOT NULL,
    supplier_code   VARCHAR(100),
    priority        SMALLINT DEFAULT 1,
    last_price      DECIMAL(12,4),
    last_price_date DATE,
    currency        VARCHAR(3) DEFAULT 'EUR',
    lead_time_days  INTEGER,
    moq             INTEGER,
    order_multiple  INTEGER,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE component_alternatives (
    component_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    alternative_id  UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    priority        SMALLINT DEFAULT 1,
    auto_approved   BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    PRIMARY KEY (component_id, alternative_id)
);

-- ============================================
-- SCHEMA: BOM (Distinte Base)
-- ============================================

CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_code    VARCHAR(30) UNIQUE NOT NULL,
    description     VARCHAR(500),
    version         VARCHAR(10) DEFAULT '1.0',
    status          VARCHAR(20) DEFAULT 'DRAFT',  -- DRAFT, ACTIVE, OBSOLETE
    cycle_time_min  INTEGER,
    production_notes TEXT,
    special_instructions TEXT,
    approved_by     VARCHAR(50),
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      VARCHAR(50)
);

CREATE TABLE bom_lines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    component_id    UUID NOT NULL REFERENCES components(id),
    quantity        DECIMAL(10,4) NOT NULL,
    reference       VARCHAR(200),                  -- designatori: R1,R2,R5,R12
    level           SMALLINT DEFAULT 1,
    phase           VARCHAR(50),                   -- SMD-TOP, SMD-BOT, THT, ASSEMBLY
    notes           TEXT,
    UNIQUE(product_id, component_id, reference)
);

-- ============================================
-- SCHEMA: WMS (Warehouse Management)
-- ============================================

CREATE TABLE warehouses (
    id              VARCHAR(20) PRIMARY KEY,       -- MAG-IT, MAG-AL, MAG-TRANSIT
    name            VARCHAR(100) NOT NULL,
    location        VARCHAR(200),
    country         VARCHAR(3),                    -- IT, AL
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE warehouse_zones (
    id              VARCHAR(30) PRIMARY KEY,       -- IT-STOCK, AL-WIP, etc.
    warehouse_id    VARCHAR(20) NOT NULL REFERENCES warehouses(id),
    name            VARCHAR(100) NOT NULL,
    zone_type       VARCHAR(20) NOT NULL,          -- INCOMING, QC, STOCK, RESERVED, WIP, FG, QUARANTINE, STAGING
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE inventory_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    barcode         VARCHAR(50) UNIQUE NOT NULL,   -- TS-RES-0805-000042-R001
    component_id    UUID NOT NULL REFERENCES components(id),
    zone_id         VARCHAR(30) NOT NULL REFERENCES warehouse_zones(id),
    quantity        DECIMAL(12,2) NOT NULL,
    quantity_unit   VARCHAR(10) DEFAULT 'PCS',
    lot_number      VARCHAR(50),
    supplier_name   VARCHAR(200),
    po_reference    VARCHAR(50),
    receive_date    DATE,
    expiry_date     DATE,
    weight_g        DECIMAL(10,2),
    status          VARCHAR(20) DEFAULT 'AVAILABLE',  -- AVAILABLE, RESERVED, BLOCKED, CONSUMED
    reserved_for    UUID,                          -- work_order_id se riservato
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE inventory_movements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         UUID NOT NULL REFERENCES inventory_items(id),
    from_zone       VARCHAR(30) REFERENCES warehouse_zones(id),
    to_zone         VARCHAR(30) REFERENCES warehouse_zones(id),
    quantity        DECIMAL(12,2) NOT NULL,
    movement_type   VARCHAR(30) NOT NULL,          -- RECEIVE, TRANSFER, SHIP, CONSUME, RETURN, SCRAP, ADJUST
    reference_type  VARCHAR(30),                   -- SHIPMENT, WORK_ORDER, QC_RESULT, MANUAL
    reference_id    UUID,
    operator        VARCHAR(50),
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- SCHEMA: SPEDIZIONI IT↔AL
-- ============================================

CREATE TABLE shipments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_code   VARCHAR(30) UNIQUE NOT NULL,   -- SHIP-2026-001
    direction       VARCHAR(10) NOT NULL,           -- IT_TO_AL, AL_TO_IT
    status          VARCHAR(20) DEFAULT 'PREPARING',
    -- PREPARING, READY, SHIPPED, IN_TRANSIT, DELIVERED, CUSTOMS_HOLD
    ship_date       DATE,
    expected_arrival DATE,
    actual_arrival  DATE,
    total_weight_kg DECIMAL(8,2),
    total_value_eur DECIMAL(12,2),
    total_packages  INTEGER,
    customs_doc_ref VARCHAR(100),
    tracking_number VARCHAR(100),
    carrier         VARCHAR(100),
    notes           TEXT,
    created_by      VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE shipment_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id     UUID NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    item_id         UUID NOT NULL REFERENCES inventory_items(id),
    quantity        DECIMAL(12,2) NOT NULL,
    customs_value   DECIMAL(10,4),
    customs_weight  DECIMAL(10,4)
);

-- ============================================
-- SCHEMA: PRODUZIONE (MES)
-- ============================================

CREATE TABLE work_orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wo_code         VARCHAR(30) UNIQUE NOT NULL,   -- WO-2026-0042
    product_id      UUID NOT NULL REFERENCES products(id),
    bom_version     VARCHAR(10),
    quantity_planned INTEGER NOT NULL,
    quantity_good   INTEGER DEFAULT 0,
    quantity_scrap  INTEGER DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'PLANNED',
    -- PLANNED, MATERIAL_CHECK, READY, IN_PROGRESS, COMPLETED, CLOSED
    site            VARCHAR(10) DEFAULT 'AL',      -- IT o AL
    planned_start   DATE,
    planned_end     DATE,
    actual_start    TIMESTAMPTZ,
    actual_end      TIMESTAMPTZ,
    customer_order  VARCHAR(50),
    priority        SMALLINT DEFAULT 5,            -- 1=urgente, 10=basso
    notes           TEXT,
    created_by      VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE wo_phases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_order_id   UUID NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    phase_name      VARCHAR(50) NOT NULL,          -- SERIGRAFIA, PICK_PLACE, REFLOW, AOI, WAVE, TEST, ASSEMBLY
    sequence        SMALLINT NOT NULL,
    status          VARCHAR(20) DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, COMPLETED, SKIPPED
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    operator        VARCHAR(50),
    qty_input       INTEGER,
    qty_output      INTEGER,
    qty_scrap       INTEGER DEFAULT 0,
    scrap_reason    TEXT,
    setup_time_min  INTEGER,
    notes           TEXT
);

CREATE TABLE wo_material_consumption (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_order_id   UUID NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    item_id         UUID NOT NULL REFERENCES inventory_items(id),
    component_id    UUID NOT NULL REFERENCES components(id),
    quantity_planned DECIMAL(10,2),
    quantity_used   DECIMAL(10,2),
    quantity_scrap  DECIMAL(10,2) DEFAULT 0,
    is_alternative  BOOLEAN DEFAULT FALSE,
    phase           VARCHAR(50),
    consumed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- SCHEMA: MRP
-- ============================================

CREATE TABLE mrp_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date        TIMESTAMPTZ DEFAULT NOW(),
    run_by          VARCHAR(50),
    horizon_days    INTEGER DEFAULT 30,
    parameters      JSONB,
    status          VARCHAR(20) DEFAULT 'RUNNING', -- RUNNING, COMPLETED, FAILED
    completed_at    TIMESTAMPTZ,
    summary         JSONB
);

CREATE TABLE mrp_suggestions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mrp_run_id      UUID NOT NULL REFERENCES mrp_runs(id) ON DELETE CASCADE,
    suggestion_type VARCHAR(20) NOT NULL,           -- PURCHASE, SHIP_TO_AL, ALERT
    component_id    UUID NOT NULL REFERENCES components(id),
    quantity_needed DECIMAL(12,2),
    quantity_available DECIMAL(12,2),
    quantity_to_order DECIMAL(12,2),
    suggested_supplier VARCHAR(200),
    order_by_date   DATE,
    need_by_date    DATE,
    priority        VARCHAR(10) DEFAULT 'MEDIUM',  -- CRITICAL, HIGH, MEDIUM, LOW
    status          VARCHAR(20) DEFAULT 'OPEN',    -- OPEN, ACCEPTED, ORDERED, DISMISSED
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- SCHEMA: QUALITÀ
-- ============================================

CREATE TABLE quality_inspections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         UUID REFERENCES inventory_items(id),
    work_order_id   UUID REFERENCES work_orders(id),
    inspection_type VARCHAR(20) NOT NULL,           -- INCOMING, IN_PROCESS, FINAL
    result          VARCHAR(15),                    -- PASS, FAIL, CONDITIONAL
    inspector       VARCHAR(50),
    sample_size     INTEGER,
    defects_found   TEXT,
    measurements    JSONB,
    photos          TEXT[],
    notes           TEXT,
    inspected_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE non_conformities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nc_code         VARCHAR(30) UNIQUE NOT NULL,   -- NC-2026-001
    source          VARCHAR(30) NOT NULL,           -- INCOMING, PRODUCTION, CUSTOMER
    component_id    UUID REFERENCES components(id),
    work_order_id   UUID REFERENCES work_orders(id),
    item_id         UUID REFERENCES inventory_items(id),
    supplier_name   VARCHAR(200),
    quantity_affected INTEGER,
    description     TEXT NOT NULL,
    root_cause      TEXT,
    corrective_action TEXT,
    preventive_action TEXT,
    status          VARCHAR(20) DEFAULT 'OPEN',    -- OPEN, INVESTIGATING, RESOLVED, CLOSED
    severity        VARCHAR(10) DEFAULT 'MEDIUM',  -- LOW, MEDIUM, HIGH, CRITICAL
    created_by      VARCHAR(50),
    assigned_to     VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);

-- ============================================
-- SCHEMA: SEQUENZE PER CODIFICA
-- ============================================

CREATE TABLE code_sequences (
    category        VARCHAR(10) NOT NULL,
    subcategory     VARCHAR(20) NOT NULL,
    last_sequence   INTEGER DEFAULT 0,
    PRIMARY KEY (category, subcategory)
);

CREATE TABLE shipment_sequences (
    year            INTEGER NOT NULL PRIMARY KEY,
    last_sequence   INTEGER DEFAULT 0
);

CREATE TABLE wo_sequences (
    year            INTEGER NOT NULL PRIMARY KEY,
    last_sequence   INTEGER DEFAULT 0
);

CREATE TABLE nc_sequences (
    year            INTEGER NOT NULL PRIMARY KEY,
    last_sequence   INTEGER DEFAULT 0
);

-- ============================================
-- INDICI PRINCIPALI
-- ============================================

CREATE INDEX idx_components_mpn ON components(mpn);
CREATE INDEX idx_components_category ON components(category);
CREATE INDEX idx_components_danea ON components(danea_code);
CREATE INDEX idx_components_manufacturer ON components(manufacturer);

CREATE INDEX idx_comp_suppliers_component ON component_suppliers(component_id);

CREATE INDEX idx_bom_product ON bom_lines(product_id);
CREATE INDEX idx_bom_component ON bom_lines(component_id);

CREATE INDEX idx_inventory_component ON inventory_items(component_id);
CREATE INDEX idx_inventory_zone ON inventory_items(zone_id);
CREATE INDEX idx_inventory_barcode ON inventory_items(barcode);
CREATE INDEX idx_inventory_status ON inventory_items(status);

CREATE INDEX idx_movements_item ON inventory_movements(item_id);
CREATE INDEX idx_movements_date ON inventory_movements(created_at);
CREATE INDEX idx_movements_type ON inventory_movements(movement_type);

CREATE INDEX idx_shipments_status ON shipments(status);
CREATE INDEX idx_shipments_direction ON shipments(direction);
CREATE INDEX idx_shipment_items_shipment ON shipment_items(shipment_id);

CREATE INDEX idx_wo_status ON work_orders(status);
CREATE INDEX idx_wo_product ON work_orders(product_id);
CREATE INDEX idx_wo_site ON work_orders(site);

CREATE INDEX idx_wo_phases_wo ON wo_phases(work_order_id);
CREATE INDEX idx_wo_consumption_wo ON wo_material_consumption(work_order_id);

CREATE INDEX idx_mrp_suggestions_run ON mrp_suggestions(mrp_run_id);
CREATE INDEX idx_mrp_suggestions_component ON mrp_suggestions(component_id);
CREATE INDEX idx_mrp_suggestions_status ON mrp_suggestions(status);

CREATE INDEX idx_qi_item ON quality_inspections(item_id);
CREATE INDEX idx_qi_wo ON quality_inspections(work_order_id);
CREATE INDEX idx_nc_status ON non_conformities(status);
CREATE INDEX idx_nc_component ON non_conformities(component_id);

-- ============================================
-- TRIGGER: updated_at automatico
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_components_updated_at
    BEFORE UPDATE ON components
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_inventory_items_updated_at
    BEFORE UPDATE ON inventory_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_shipments_updated_at
    BEFORE UPDATE ON shipments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_work_orders_updated_at
    BEFORE UPDATE ON work_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
