# Shapefile Import Pipeline for Tanzania Land Plots

## Overview
This guide covers importing Tanzania land plot shapefiles into the PostGIS database with proper coordinate transformation and attribute handling.

## Prerequisites
- GDAL/OGR tools installed
- Access to PostGIS database (Supabase)
- Tanzania land plot shapefiles (.shp, .shx, .dbf, .prj, .cpg)

## Common Tanzania Coordinate Systems

### Input Coordinate Systems (Shapefile Sources)
- **Arc 1960 UTM Zone 36S**: EPSG:21096
- **Arc 1960 UTM Zone 37S**: EPSG:21097
- **WGS 84 UTM Zone 36S**: EPSG:32736
- **WGS 84 UTM Zone 37S**: EPSG:32737
- **Tanzania National Grid**: Custom CRS

### Output System
- **WGS 84**: EPSG:4326 (for web mapping)

## Step 1: Inspect Shapefile

```bash
# Get basic information about the shapefile
ogrinfo -al your_tanzania_plots.shp

# Check coordinate reference system
ogrinfo -so your_tanzania_plots.shp layer_name

# List available attributes
ogrinfo -sql "SELECT * FROM layer_name LIMIT 1" your_tanzania_plots.shp
```

Expected output:
```
Layer name: tanzania_plots
Geometry: Polygon
Feature Count: 1500
Extent: (500000.000000, 9200000.000000) - (600000.000000, 9300000.000000)
Layer SRS WKT:
PROJCS["Arc_1960_UTM_Zone_36S"...]

Attributes:
- PLOT_CODE: String (20)
- DISTRICT: String (50)
- WARD: String (50)
- VILLAGE: String (50)
- AREA_HA: Real (10.4)
- LAND_USE: String (30)
- STATUS: String (20)
```

## Step 2: Prepare Database Connection

```bash
# Set database connection string
export PG_CONNECTION="PG:host=db.supabaseproject.co port=5432 dbname=postgres user=postgres password=yourpassword sslmode=require"

# Test connection
psql "postgresql://postgres:yourpassword@db.supabaseproject.co:5432/postgres?sslmode=require" -c "SELECT version();"
```

## Step 3: Import Shapefile

### Basic Import with Transformation
```bash
ogr2ogr -f "PostgreSQL" \
  "$PG_CONNECTION" \
  your_tanzania_plots.shp \
  -nln land_plots_import \
  -t_srs EPSG:4326 \
  -s_srs EPSG:21096 \
  -overwrite \
  -progress \
  -lco GEOMETRY_NAME=geometry \
  -lco PRECISION=NO
```

### Advanced Import with Attribute Mapping
```bash
ogr2ogr -f "PostgreSQL" \
  "$PG_CONNECTION" \
  your_tanzania_plots.shp \
  -nln land_plots_import \
  -t_srs EPSG:4326 \
  -s_srs EPSG:21096 \
  -overwrite \
  -progress \
  -lco GEOMETRY_NAME=geometry \
  -lco PRECISION=NO \
  -sql "SELECT 
    PLOT_CODE as plot_code,
    DISTRICT as district,
    WARD as ward, 
    VILLAGE as village,
    AREA_HA as area_hectares,
    LAND_USE as land_use,
    CASE 
      WHEN STATUS = 'OCCUPIED' THEN 'taken'
      WHEN STATUS = 'RESERVED' THEN 'pending'
      ELSE 'available'
    END as status,
    * 
    FROM your_tanzania_plots"
```

### Parameters Explanation
- `-f "PostgreSQL"`: Output format
- `-nln`: New layer name in database
- `-t_srs`: Target spatial reference system
- `-s_srs`: Source spatial reference system
- `-overwrite`: Replace existing table
- `-progress`: Show progress
- `-lco GEOMETRY_NAME`: Name for geometry column
- `-sql`: Custom SQL to transform attributes

## Step 4: Process Imported Data

```sql
-- Connect to database and process the imported data
\c your_database

-- Inspect imported data
SELECT 
  COUNT(*) as total_plots,
  ST_GeometryType(geometry) as geom_type,
  ST_SRID(geometry) as srid
FROM land_plots_import;

-- Check for invalid geometries
SELECT ogc_fid, ST_IsValid(geometry), ST_IsValidReason(geometry)
FROM land_plots_import 
WHERE NOT ST_IsValid(geometry);

-- Fix invalid geometries if any
UPDATE land_plots_import 
SET geometry = ST_MakeValid(geometry) 
WHERE NOT ST_IsValid(geometry);

-- Convert to MultiPolygon and calculate area
INSERT INTO land_plots (
  plot_code, 
  status, 
  area_hectares, 
  district, 
  ward, 
  village, 
  geometry, 
  attributes
)
SELECT 
  COALESCE(plot_code, 'PLOT_' || row_number() OVER()) as plot_code,
  COALESCE(
    CASE 
      WHEN UPPER(status) IN ('OCCUPIED', 'TAKEN') THEN 'taken'
      WHEN UPPER(status) IN ('RESERVED', 'PENDING') THEN 'pending'
      ELSE 'available'
    END, 
    'available'
  ) as status,
  COALESCE(
    area_hectares, 
    -- Calculate area in hectares if not provided
    ST_Area(ST_Transform(geometry, 32737)) / 10000.0
  ) as area_hectares,
  COALESCE(district, 'Unknown') as district,
  COALESCE(ward, 'Unknown') as ward,
  COALESCE(village, 'Unknown') as village,
  -- Ensure MultiPolygon type
  CASE 
    WHEN ST_GeometryType(geometry) = 'ST_Polygon' THEN ST_Multi(geometry)
    ELSE geometry
  END as geometry,
  -- Store all original attributes as JSONB
  to_jsonb(
    json_build_object(
      'original_area', area_hectares,
      'land_use', land_use,
      'import_date', now(),
      'source_file', 'shapefile_import'
    ) || 
    (SELECT jsonb_object_agg(key, value) 
     FROM jsonb_each_text(to_jsonb(land_plots_import.*)) 
     WHERE key NOT IN ('ogc_fid', 'geometry', 'plot_code', 'status', 'area_hectares', 'district', 'ward', 'village'))
  ) as attributes
FROM land_plots_import
-- Avoid duplicates
WHERE NOT EXISTS (
  SELECT 1 FROM land_plots 
  WHERE land_plots.plot_code = land_plots_import.plot_code
);

-- Clean up import table
DROP TABLE land_plots_import;

-- Verify the import
SELECT 
  COUNT(*) as total_plots,
  COUNT(*) FILTER (WHERE status = 'available') as available_plots,
  COUNT(*) FILTER (WHERE status = 'taken') as taken_plots,
  COUNT(*) FILTER (WHERE status = 'pending') as pending_plots,
  AVG(area_hectares) as avg_area_hectares,
  COUNT(DISTINCT district) as districts,
  COUNT(DISTINCT ward) as wards
FROM land_plots;
```

## Step 5: Data Quality Checks

```sql
-- Check for duplicate plot codes
SELECT plot_code, COUNT(*) 
FROM land_plots 
GROUP BY plot_code 
HAVING COUNT(*) > 1;

-- Check geometry validity
SELECT COUNT(*) as invalid_geometries
FROM land_plots 
WHERE NOT ST_IsValid(geometry);

-- Check coordinate bounds (should be in Tanzania)
SELECT 
  ST_XMin(ST_Extent(geometry)) as min_lon,
  ST_YMin(ST_Extent(geometry)) as min_lat,
  ST_XMax(ST_Extent(geometry)) as max_lon,
  ST_YMax(ST_Extent(geometry)) as max_lat
FROM land_plots;
-- Expected: roughly lon 29-41, lat -12 to -1

-- Check area distribution
SELECT 
  MIN(area_hectares) as min_area,
  MAX(area_hectares) as max_area,
  AVG(area_hectares) as avg_area,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY area_hectares) as median_area
FROM land_plots;
```

## Step 6: Create Spatial Index

```sql
-- Create spatial index for performance
CREATE INDEX IF NOT EXISTS idx_land_plots_geometry_gist 
ON land_plots USING GIST (geometry);

-- Create additional indexes
CREATE INDEX IF NOT EXISTS idx_land_plots_district 
ON land_plots (district);

CREATE INDEX IF NOT EXISTS idx_land_plots_status 
ON land_plots (status);

-- Analyze table for query optimization
ANALYZE land_plots;
```

## Common Issues and Solutions

### Issue 1: Unknown Coordinate System
**Error**: `Cannot find coordinate system for EPSG:XXXX`

**Solution**: 
```bash
# Add custom projection if needed
ogr2ogr -f "PostgreSQL" \
  "$PG_CONNECTION" \
  your_plots.shp \
  -t_srs EPSG:4326 \
  -s_srs "+proj=utm +zone=37 +south +datum=WGS84" \
  -nln land_plots_import
```

### Issue 2: Large File Import
**For files >500MB**:
```bash
# Use chunked import
ogr2ogr -f "PostgreSQL" \
  "$PG_CONNECTION" \
  large_plots.shp \
  -nln land_plots_import \
  -t_srs EPSG:4326 \
  -gt 1000 \
  -progress \
  --config PG_USE_COPY YES
```

### Issue 3: Encoding Issues
**For Swahili characters**:
```bash
ogr2ogr -f "PostgreSQL" \
  "$PG_CONNECTION" \
  plots_with_swahili.shp \
  -nln land_plots_import \
  -lco ENCODING=UTF-8 \
  -t_srs EPSG:4326
```

## Batch Processing Script

Create `import_shapefiles.sh`:
```bash
#!/bin/bash

# Configuration
DB_CONNECTION="PG:host=db.supabaseproject.co port=5432 dbname=postgres user=postgres password=$DB_PASSWORD sslmode=require"
SHAPEFILE_DIR="/path/to/shapefiles"

# Process all shapefiles in directory
for shapefile in "$SHAPEFILE_DIR"/*.shp; do
    echo "Processing: $shapefile"
    
    # Extract filename without extension
    basename=$(basename "$shapefile" .shp)
    
    # Import with transformation
    ogr2ogr -f "PostgreSQL" \
        "$DB_CONNECTION" \
        "$shapefile" \
        -nln "import_$basename" \
        -t_srs EPSG:4326 \
        -overwrite \
        -progress
        
    echo "Completed: $shapefile"
done

echo "All shapefiles imported. Run SQL processing script next."
```

## Performance Tips

1. **Use chunked imports** (`-gt` parameter) for large files
2. **Enable COPY mode** (`--config PG_USE_COPY YES`) for faster inserts  
3. **Import to temporary tables** first, then process
4. **Create indexes after import**, not before
5. **Use connection pooling** for multiple imports
6. **Monitor memory usage** with large geometries

This pipeline handles the complete workflow from raw Tanzania shapefiles to production-ready spatial data in your PostGIS database.