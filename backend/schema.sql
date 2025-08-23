-- PostgreSQL/PostGIS DDL for Tanzania Land Plot Ordering MVS
-- Safe to run multiple times (uses IF NOT EXISTS where possible)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid

-- Land plots table
CREATE TABLE IF NOT EXISTS public.land_plots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_code text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available','taken','pending')),
  area_hectares numeric(12,4) NOT NULL CHECK (area_hectares > 0),
  district text NOT NULL,
  ward text NOT NULL,
  village text NOT NULL,
  dataset_name text,
  geometry geometry(MultiPolygon,4326) NOT NULL,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Orders table
CREATE TABLE IF NOT EXISTS public.plot_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plot_id uuid NOT NULL REFERENCES public.land_plots(id) ON DELETE CASCADE,
    customer_name text NOT NULL,
    customer_phone text NOT NULL,
    customer_email text,
    customer_id_number text NOT NULL,
    intended_use text NOT NULL CHECK (intended_use IN ('residential','commercial','agricultural','industrial','mixed')),
    notes text,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_land_plots_status ON public.land_plots(status);
CREATE INDEX IF NOT EXISTS idx_land_plots_district ON public.land_plots(lower(district));
CREATE INDEX IF NOT EXISTS idx_land_plots_ward ON public.land_plots(lower(ward));
CREATE INDEX IF NOT EXISTS idx_land_plots_village ON public.land_plots(lower(village));
CREATE INDEX IF NOT EXISTS idx_land_plots_geom ON public.land_plots USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_land_plots_dataset ON public.land_plots(dataset_name);
CREATE INDEX IF NOT EXISTS idx_plot_orders_plot_id ON public.plot_orders(plot_id);
CREATE INDEX IF NOT EXISTS idx_plot_orders_status ON public.plot_orders(status);
CREATE INDEX IF NOT EXISTS idx_plot_orders_customer_id_number ON public.plot_orders(customer_id_number);

-- Trigger to keep updated_at current
CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_land_plots_updated_at'
  ) THEN
    CREATE TRIGGER trg_land_plots_updated_at
    BEFORE UPDATE ON public.land_plots
    FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_plot_orders_updated_at'
  ) THEN
    CREATE TRIGGER trg_plot_orders_updated_at
    BEFORE UPDATE ON public.plot_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at_timestamp();
  END IF;
END$$;

-- Track original shapefile components & metadata
CREATE TABLE IF NOT EXISTS public.shapefile_imports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_name text NOT NULL UNIQUE,
  prj text,
  cpg text,
  dbf_schema jsonb,
  file_hashes jsonb,
  feature_count integer,
  bbox geometry(Polygon,4326),
  imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shapefile_imports_bbox ON public.shapefile_imports USING GIST (bbox);
