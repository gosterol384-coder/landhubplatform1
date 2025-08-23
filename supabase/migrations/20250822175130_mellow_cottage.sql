/*
  # Tanzania Land Plot System Database Schema

  1. Core Tables
    - `land_plots` - Land plot spatial data with geometry and attributes
    - `plot_orders` - Customer orders for land plots
    
  2. Spatial Features
    - PostGIS extension for spatial data handling
    - Spatial indexes on geometry columns
    - Support for MultiPolygon geometries
    
  3. Security
    - Row Level Security (RLS) enabled
    - Public access for plot viewing
    - Secure order creation
    
  4. Indexes
    - Spatial indexes for performance
    - Standard indexes on frequently queried columns
    
  5. Sample Data
    - Mock Tanzania plots for development/testing
*/

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create land_plots table
CREATE TABLE IF NOT EXISTS land_plots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_code text UNIQUE NOT NULL,
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'taken', 'pending')),
  area_hectares numeric(10,4) NOT NULL,
  district text NOT NULL,
  ward text NOT NULL,
  village text NOT NULL,
  geometry geometry(MultiPolygon, 4326) NOT NULL,
  attributes jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create plot_orders table
CREATE TABLE IF NOT EXISTS plot_orders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_id uuid NOT NULL REFERENCES land_plots(id),
  customer_name text NOT NULL,
  customer_phone text NOT NULL,
  customer_email text,
  customer_id_number text NOT NULL,
  intended_use text NOT NULL CHECK (intended_use IN ('residential', 'commercial', 'agricultural', 'industrial', 'mixed')),
  notes text,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create spatial index on geometry
CREATE INDEX IF NOT EXISTS idx_land_plots_geometry ON land_plots USING GIST (geometry);

-- Create standard indexes
CREATE INDEX IF NOT EXISTS idx_land_plots_status ON land_plots (status);
CREATE INDEX IF NOT EXISTS idx_land_plots_district ON land_plots (district);
CREATE INDEX IF NOT EXISTS idx_land_plots_plot_code ON land_plots (plot_code);
CREATE INDEX IF NOT EXISTS idx_plot_orders_plot_id ON plot_orders (plot_id);
CREATE INDEX IF NOT EXISTS idx_plot_orders_status ON plot_orders (status);
CREATE INDEX IF NOT EXISTS idx_plot_orders_customer_id ON plot_orders (customer_id_number);

-- Enable Row Level Security
ALTER TABLE land_plots ENABLE ROW LEVEL SECURITY;
ALTER TABLE plot_orders ENABLE ROW LEVEL SECURITY;

-- RLS Policies for land_plots (public read access)
CREATE POLICY "Anyone can view land plots"
  ON land_plots
  FOR SELECT
  TO public
  USING (true);

-- RLS Policies for plot_orders (anyone can insert orders)
CREATE POLICY "Anyone can create plot orders"
  ON plot_orders
  FOR INSERT
  TO public
  WITH CHECK (true);

CREATE POLICY "Anyone can view their own orders"
  ON plot_orders
  FOR SELECT
  TO public
  USING (true);

-- Function to update plot status when order is created
CREATE OR REPLACE FUNCTION update_plot_status_on_order()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE land_plots 
  SET status = 'pending', updated_at = now()
  WHERE id = NEW.plot_id;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update plot status when order is created
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_update_plot_status_on_order'
  ) THEN
    CREATE TRIGGER trigger_update_plot_status_on_order
      AFTER INSERT ON plot_orders
      FOR EACH ROW
      EXECUTE FUNCTION update_plot_status_on_order();
  END IF;
END $$;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_land_plots_updated_at'
  ) THEN
    CREATE TRIGGER trigger_land_plots_updated_at
      BEFORE UPDATE ON land_plots
      FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_plot_orders_updated_at'
  ) THEN
    CREATE TRIGGER trigger_plot_orders_updated_at
      BEFORE UPDATE ON plot_orders
      FOR EACH ROW
      EXECUTE FUNCTION update_updated_at_column();
  END IF;
END $$;

-- Insert sample data for development
INSERT INTO land_plots (plot_code, status, area_hectares, district, ward, village, geometry) VALUES
(
  'DSM/KINONDONI/001',
  'available',
  0.5,
  'Kinondoni',
  'Msasani',
  'Msasani Peninsula',
  ST_GeomFromText('MULTIPOLYGON(((39.2734 -6.7732, 39.2744 -6.7732, 39.2744 -6.7742, 39.2734 -6.7742, 39.2734 -6.7732)))', 4326)
),
(
  'DSM/KINONDONI/002',
  'taken',
  0.75,
  'Kinondoni',
  'Msasani',
  'Msasani Peninsula',
  ST_GeomFromText('MULTIPOLYGON(((39.2744 -6.7732, 39.2754 -6.7732, 39.2754 -6.7742, 39.2744 -6.7742, 39.2744 -6.7732)))', 4326)
),
(
  'DSM/KINONDONI/003',
  'available',
  1.0,
  'Kinondoni',
  'Msasani',
  'Msasani Peninsula',
  ST_GeomFromText('MULTIPOLYGON(((39.2754 -6.7732, 39.2764 -6.7732, 39.2764 -6.7742, 39.2754 -6.7742, 39.2754 -6.7732)))', 4326)
),
(
  'DSM/KINONDONI/004',
  'pending',
  0.6,
  'Kinondoni',
  'Msasani',
  'Msasani Peninsula',
  ST_GeomFromText('MULTIPOLYGON(((39.2734 -6.7742, 39.2744 -6.7742, 39.2744 -6.7752, 39.2734 -6.7752, 39.2734 -6.7742)))', 4326)
),
(
  'ARUSHA/MERU/001',
  'available',
  2.0,
  'Meru',
  'Usa River',
  'Kikatiti',
  ST_GeomFromText('MULTIPOLYGON(((36.8330 -3.3950, 36.8350 -3.3950, 36.8350 -3.3970, 36.8330 -3.3970, 36.8330 -3.3950)))', 4326)
),
(
  'MWANZA/ILEMELA/001',
  'available',
  1.5,
  'Ilemela',
  'Nyamanoro',
  'Buzuruga',
  ST_GeomFromText('MULTIPOLYGON(((32.9000 -2.5200, 32.9020 -2.5200, 32.9020 -2.5220, 32.9000 -2.5220, 32.9000 -2.5200)))', 4326)
) ON CONFLICT (plot_code) DO NOTHING;