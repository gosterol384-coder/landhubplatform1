#!/usr/bin/env python3
"""
Enhanced seed script for Tanzania Land Plot System
Imports shapefile data with proper coordinate transformation and validation
"""

import os
import sys
import json
import logging
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import engine, SessionLocal
from models import LandPlot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ShapefileImporter:
    """Enhanced shapefile importer with comprehensive error handling"""
    
    def __init__(self, db_session):
        self.db = db_session
        self.temp_table = "temp_shapefile_import"
        
    def check_gdal_availability(self) -> bool:
        """Check if GDAL/OGR tools are available"""
        try:
            subprocess.run(['ogr2ogr', '--version'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("GDAL/OGR tools not available, using fallback method")
            return False
    
    def get_shapefile_info(self, shapefile_path: str) -> Dict:
        """Extract metadata from shapefile"""
        info = {
            'path': shapefile_path,
            'exists': os.path.exists(shapefile_path),
            'size': 0,
            'crs': None,
            'feature_count': 0,
            'bounds': None,
            'fields': []
        }
        
        if not info['exists']:
            return info
            
        info['size'] = os.path.getsize(shapefile_path)
        
        # Try to get info using ogrinfo if available
        try:
            result = subprocess.run([
                'ogrinfo', '-so', '-al', shapefile_path
            ], capture_output=True, text=True, check=True)
            
            output = result.stdout
            
            # Parse feature count
            for line in output.split('\n'):
                if 'Feature Count:' in line:
                    try:
                        info['feature_count'] = int(line.split(':')[1].strip())
                    except:
                        pass
                elif 'Extent:' in line:
                    # Parse extent
                    try:
                        extent_str = line.split('Extent:')[1].strip()
                        # Format: (minx, miny) - (maxx, maxy)
                        coords = extent_str.replace('(', '').replace(')', '').replace(' - ', ',').split(',')
                        if len(coords) == 4:
                            info['bounds'] = [float(c.strip()) for c in coords]
                    except:
                        pass
                elif ':' in line and '(' in line and ')' in line:
                    # Parse field definitions
                    try:
                        field_name = line.split(':')[0].strip()
                        field_type = line.split('(')[0].split(':')[1].strip()
                        if field_name and field_type and not field_name.startswith('Layer'):
                            info['fields'].append({
                                'name': field_name,
                                'type': field_type
                            })
                    except:
                        pass
                        
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Could not get shapefile info using ogrinfo")
            
        return info
    
    def import_with_ogr2ogr(self, shapefile_path: str) -> bool:
        """Import shapefile using ogr2ogr"""
        if not self.check_gdal_availability():
            return False
            
        try:
            # Build connection string
            db_url = engine.url
            pg_conn = f"PG:host={db_url.host} port={db_url.port or 5432} dbname={db_url.database} user={db_url.username} password={db_url.password}"
            
            # Drop existing temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            self.db.commit()
            
            # Import with coordinate transformation
            cmd = [
                'ogr2ogr',
                '-f', 'PostgreSQL',
                pg_conn,
                shapefile_path,
                '-nln', self.temp_table,
                '-nlt', 'MULTIPOLYGON',
                '-t_srs', 'EPSG:4326',
                '-lco', 'GEOMETRY_NAME=geometry',
                '-lco', 'PRECISION=NO',
                '-overwrite',
                '-progress'
            ]
            
            logger.info(f"Running ogr2ogr import: {' '.join(cmd[:3])} ...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if result.returncode == 0:
                logger.info("ogr2ogr import completed successfully")
                return True
            else:
                logger.error(f"ogr2ogr failed: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"ogr2ogr import failed: {e}")
            logger.error(f"stderr: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in ogr2ogr import: {e}")
            return False
    
    def import_with_fallback(self, shapefile_path: str) -> bool:
        """Fallback import using Python libraries"""
        try:
            import fiona
            from shapely.geometry import shape, mapping
            from shapely.ops import transform
            import pyproj
        except ImportError:
            logger.error("Fallback libraries (fiona, shapely, pyproj) not available")
            return False
            
        try:
            # Drop existing temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            
            # Create temp table
            self.db.execute(text(f"""
                CREATE TABLE {self.temp_table} (
                    id SERIAL PRIMARY KEY,
                    geometry geometry(MultiPolygon, 4326),
                    attributes JSONB
                )
            """))
            self.db.commit()
            
            with fiona.open(shapefile_path) as src:
                # Setup coordinate transformation
                source_crs = src.crs
                target_crs = pyproj.CRS.from_epsg(4326)
                
                transformer = None
                if source_crs and source_crs != target_crs:
                    source_proj = pyproj.CRS(source_crs)
                    transformer = pyproj.Transformer.from_crs(
                        source_proj, target_crs, always_xy=True
                    )
                
                # Import features
                for feature in src:
                    geom = shape(feature['geometry'])
                    
                    # Transform coordinates if needed
                    if transformer:
                        geom = transform(transformer.transform, geom)
                    
                    # Ensure MultiPolygon
                    if geom.geom_type == 'Polygon':
                        from shapely.geometry import MultiPolygon
                        geom = MultiPolygon([geom])
                    
                    # Insert into temp table
                    self.db.execute(text(f"""
                        INSERT INTO {self.temp_table} (geometry, attributes)
                        VALUES (ST_GeomFromGeoJSON(:geom), :attrs)
                    """), {
                        'geom': json.dumps(mapping(geom)),
                        'attrs': json.dumps(feature['properties'] or {})
                    })
                
                self.db.commit()
                logger.info("Fallback import completed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Fallback import failed: {e}")
            self.db.rollback()
            return False
    
    def process_imported_data(self, dataset_name: str, district: str, ward: str, village: str) -> int:
        """Process imported data into land_plots table"""
        try:
            # Check if temp table exists and has data
            result = self.db.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = '{self.temp_table}'
            """)).scalar()
            
            if not result:
                raise Exception(f"Temporary table {self.temp_table} does not exist")
            
            # Get count of imported records
            imported_count = self.db.execute(text(f"SELECT COUNT(*) FROM {self.temp_table}")).scalar()
            logger.info(f"Processing {imported_count} imported records")
            
            if imported_count == 0:
                raise Exception("No data found in temporary table")
            
            # Check table structure
            columns = self.db.execute(text(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{self.temp_table}'
                ORDER BY ordinal_position
            """)).fetchall()
            
            logger.info(f"Temp table columns: {[col[0] for col in columns]}")
            
            # Determine if we have attributes column (fallback method) or individual columns (ogr2ogr)
            has_attributes_col = any(col[0] == 'attributes' for col in columns)
            
            if has_attributes_col:
                # Fallback method - data is in attributes JSONB column
                insert_sql = f"""
                    INSERT INTO land_plots (
                        plot_code, status, area_hectares, district, ward, village,
                        dataset_name, geometry, attributes, created_at, updated_at
                    )
                    SELECT 
                        COALESCE(
                            attributes->>'plot_code',
                            attributes->>'PLOT_CODE',
                            attributes->>'plotcode',
                            attributes->>'code',
                            '{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY id)::text, 4, '0')
                        ) as plot_code,
                        'available' as status,
                        COALESCE(
                            CAST(NULLIF(attributes->>'area_ha', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'AREA_HA', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'area', '') AS NUMERIC),
                            ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS NUMERIC), 4)
                        ) as area_hectares,
                        :district as district,
                        :ward as ward,
                        :village as village,
                        :dataset_name as dataset_name,
                        ST_Multi(ST_Force2D(geometry))::geometry(MultiPolygon,4326) as geometry,
                        attributes,
                        NOW() as created_at,
                        NOW() as updated_at
                    FROM {self.temp_table}
                    WHERE geometry IS NOT NULL
                    ON CONFLICT (plot_code) DO NOTHING
                """
            else:
                # ogr2ogr method - data is in individual columns
                # Build attributes JSON from available columns
                attr_columns = [col[0] for col in columns if col[0] not in ['id', 'geometry', 'ogc_fid', 'wkb_geometry']]
                
                if attr_columns:
                    json_pairs = []
                    for col in attr_columns:
                        json_pairs.append(f"'{col}', {col}")
                    json_build = f"jsonb_build_object({', '.join(json_pairs)})"
                else:
                    json_build = "'{}'::jsonb"
                
                # Find potential plot code column
                plot_code_col = None
                for col in attr_columns:
                    if col.lower() in ['plot_code', 'plotcode', 'code', 'plot_no', 'plotnum']:
                        plot_code_col = col
                        break
                
                plot_code_expr = (
                    f"COALESCE({plot_code_col}, '{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY ogc_fid)::text, 4, '0'))"
                    if plot_code_col else
                    f"'{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY ogc_fid)::text, 4, '0')"
                )
                
                # Find area column
                area_col = None
                for col in attr_columns:
                    if col.lower() in ['area_ha', 'area', 'hectares']:
                        area_col = col
                        break
                
                area_expr = (
                    f"COALESCE(CAST(NULLIF({area_col}, '') AS NUMERIC), ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS NUMERIC), 4))"
                    if area_col else
                    "ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS NUMERIC), 4)"
                )
                
                insert_sql = f"""
                    INSERT INTO land_plots (
                        plot_code, status, area_hectares, district, ward, village,
                        dataset_name, geometry, attributes, created_at, updated_at
                    )
                    SELECT 
                        {plot_code_expr} as plot_code,
                        'available' as status,
                        {area_expr} as area_hectares,
                        :district as district,
                        :ward as ward,
                        :village as village,
                        :dataset_name as dataset_name,
                        ST_Multi(ST_Force2D(geometry))::geometry(MultiPolygon,4326) as geometry,
                        {json_build} as attributes,
                        NOW() as created_at,
                        NOW() as updated_at
                    FROM {self.temp_table}
                    WHERE geometry IS NOT NULL
                    ON CONFLICT (plot_code) DO NOTHING
                """
            
            # Execute the insert
            result = self.db.execute(text(insert_sql), {
                'district': district,
                'ward': ward,
                'village': village,
                'dataset_name': dataset_name
            })
            
            self.db.commit()
            
            # Get count of inserted records
            inserted_count = self.db.execute(text("""
                SELECT COUNT(*) FROM land_plots 
                WHERE dataset_name = :dataset_name
            """), {'dataset_name': dataset_name}).scalar()
            
            logger.info(f"Successfully inserted {inserted_count} land plots")
            
            # Clean up temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            self.db.commit()
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"Error processing imported data: {e}")
            self.db.rollback()
            raise
    
    def import_shapefile(self, shapefile_path: str, dataset_name: str, 
                        district: str, ward: str, village: str) -> int:
        """Main import method"""
        logger.info(f"Starting shapefile import: {shapefile_path}")
        
        # Get shapefile info
        info = self.get_shapefile_info(shapefile_path)
        logger.info(f"Shapefile info: {info}")
        
        if not info['exists']:
            raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")
        
        # Try ogr2ogr first, then fallback
        success = self.import_with_ogr2ogr(shapefile_path)
        if not success:
            logger.info("Trying fallback import method...")
            success = self.import_with_fallback(shapefile_path)
        
        if not success:
            raise Exception("Both import methods failed")
        
        # Process the imported data
        return self.process_imported_data(dataset_name, district, ward, village)

def seed_sample_data():
    """Seed the database with sample Tanzania land plot data"""
    logger.info("Starting database seeding process...")
    
    # Database session
    db = SessionLocal()
    
    try:
        # Initialize importer
        importer = ShapefileImporter(db)
        
        # Path to sample shapefile
        shapefile_path = "/home/project/backend/data/test_mbuyuni/test_mbuyuni.shp"
        
        if not os.path.exists(shapefile_path):
            logger.error(f"Sample shapefile not found: {shapefile_path}")
            return False
        
        # Import the sample data
        inserted_count = importer.import_shapefile(
            shapefile_path=shapefile_path,
            dataset_name="test_mbuyuni",
            district="Mbuyuni",
            ward="Mbuyuni Ward",
            village="Mbuyuni Village"
        )
        
        logger.info(f"Successfully imported {inserted_count} land plots")
        
        # Verify the import
        total_plots = db.execute(text("SELECT COUNT(*) FROM land_plots")).scalar()
        available_plots = db.execute(text("SELECT COUNT(*) FROM land_plots WHERE status = 'available'")).scalar()
        
        logger.info(f"Database now contains {total_plots} total plots ({available_plots} available)")
        
        # Get spatial extent
        extent = db.execute(text("""
            SELECT 
                ST_XMin(ST_Extent(geometry)) as min_lon,
                ST_YMin(ST_Extent(geometry)) as min_lat,
                ST_XMax(ST_Extent(geometry)) as max_lon,
                ST_YMax(ST_Extent(geometry)) as max_lat
            FROM land_plots
        """)).fetchone()
        
        if extent:
            logger.info(f"Spatial extent: ({extent.min_lon:.6f}, {extent.min_lat:.6f}) to ({extent.max_lon:.6f}, {extent.max_lat:.6f})")
        
        return True
        
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def main():
    """Main function"""
    logger.info("Tanzania Land Plot System - Database Seeder")
    
    # Test database connection
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"Database connected: {version}")
            
            # Test PostGIS
            result = conn.execute(text("SELECT PostGIS_Version()"))
            postgis_version = result.fetchone()[0]
            logger.info(f"PostGIS version: {postgis_version}")
            
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
    
    # Run seeding
    success = seed_sample_data()
    
    if success:
        logger.info("✅ Database seeding completed successfully!")
        return True
    else:
        logger.error("❌ Database seeding failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)