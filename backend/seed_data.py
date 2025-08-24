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
from models import LandPlot, ShapefileImport

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedShapefileImporter:
    """Enhanced shapefile importer with comprehensive error handling"""
    
    def __init__(self, db_session):
        self.db = db_session
        self.temp_table = "temp_shapefile_import"
        
    def check_gdal_availability(self) -> bool:
        """Check if GDAL/OGR tools are available"""
        try:
            result = subprocess.run(['ogr2ogr', '--version'], 
                                  capture_output=True, check=True, text=True)
            logger.info(f"GDAL/OGR available: {result.stdout.strip()}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("GDAL/OGR tools not available, using fallback method")
            return False
    
    def get_shapefile_info(self, shapefile_path: str) -> Dict:
        """Extract comprehensive metadata from shapefile"""
        info = {
            'path': shapefile_path,
            'exists': os.path.exists(shapefile_path),
            'size': 0,
            'crs': None,
            'feature_count': 0,
            'bounds': None,
            'fields': [],
            'geometry_type': None
        }
        
        if not info['exists']:
            logger.error(f"Shapefile not found: {shapefile_path}")
            return info
            
        info['size'] = os.path.getsize(shapefile_path)
        logger.info(f"Shapefile size: {info['size']} bytes")
        
        # Try to get detailed info using ogrinfo
        try:
            result = subprocess.run([
                'ogrinfo', '-so', '-al', shapefile_path
            ], capture_output=True, text=True, check=True)
            
            output = result.stdout
            logger.info("Shapefile info extracted successfully")
            
            # Parse output for metadata
            for line in output.split('\n'):
                line = line.strip()
                
                if 'Feature Count:' in line:
                    try:
                        info['feature_count'] = int(line.split(':')[1].strip())
                    except:
                        pass
                        
                elif 'Extent:' in line:
                    try:
                        extent_str = line.split('Extent:')[1].strip()
                        # Parse extent coordinates
                        coords = extent_str.replace('(', '').replace(')', '').replace(' - ', ',').split(',')
                        if len(coords) == 4:
                            info['bounds'] = [float(c.strip()) for c in coords]
                    except:
                        pass
                        
                elif 'Geometry:' in line:
                    try:
                        info['geometry_type'] = line.split('Geometry:')[1].strip()
                    except:
                        pass
                        
                elif ':' in line and '(' in line and ')' in line and not line.startswith('Layer'):
                    # Parse field definitions
                    try:
                        field_name = line.split(':')[0].strip()
                        field_type = line.split('(')[0].split(':')[1].strip()
                        if field_name and field_type:
                            info['fields'].append({
                                'name': field_name,
                                'type': field_type
                            })
                    except:
                        pass
                        
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Could not get shapefile info using ogrinfo: {e}")
            
        logger.info(f"Shapefile analysis complete: {info['feature_count']} features, {len(info['fields'])} fields")
        return info
    
    def import_with_ogr2ogr(self, shapefile_path: str) -> bool:
        """Import shapefile using ogr2ogr with enhanced error handling"""
        if not self.check_gdal_availability():
            return False
            
        try:
            # Build PostgreSQL connection string
            db_url = engine.url
            pg_conn = f"PG:host={db_url.host} port={db_url.port or 5432} dbname={db_url.database} user={db_url.username} password={db_url.password}"
            
            # Drop existing temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            self.db.commit()
            
            # Enhanced ogr2ogr command with better error handling
            cmd = [
                'ogr2ogr',
                '-f', 'PostgreSQL',
                pg_conn,
                shapefile_path,
                '-nln', self.temp_table,
                '-nlt', 'MULTIPOLYGON',
                '-t_srs', 'EPSG:4326',  # Target: WGS84
                '-lco', 'GEOMETRY_NAME=geometry',
                '-lco', 'PRECISION=NO',
                '-lco', 'FID=ogc_fid',
                '-overwrite',
                '-progress',
                '--config', 'PG_USE_COPY', 'YES',  # Faster bulk insert
                '--config', 'GDAL_HTTP_TIMEOUT', '30'
            ]
            
            logger.info("Starting ogr2ogr import...")
            logger.info(f"Command: {' '.join(cmd[:5])} ... [connection details hidden]")
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if result.returncode == 0:
                logger.info("✅ ogr2ogr import completed successfully")
                
                # Verify import
                count = self.db.execute(text(f"SELECT COUNT(*) FROM {self.temp_table}")).scalar()
                logger.info(f"Imported {count} features to temporary table")
                
                return True
            else:
                logger.error(f"❌ ogr2ogr failed with return code {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ ogr2ogr import failed: {e}")
            if e.stderr:
                logger.error(f"Error details: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error in ogr2ogr import: {e}")
            return False
    
    def import_with_fallback(self, shapefile_path: str) -> bool:
        """Fallback import using Python libraries"""
        try:
            import fiona
            from shapely.geometry import shape, mapping, MultiPolygon
            from shapely.ops import transform
            import pyproj
        except ImportError as e:
            logger.error(f"❌ Fallback libraries not available: {e}")
            logger.error("Please install: pip install fiona shapely pyproj")
            return False
            
        try:
            logger.info("🔄 Using Python fallback import method...")
            
            # Drop existing temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            
            # Create temp table with proper structure
            self.db.execute(text(f"""
                CREATE TABLE {self.temp_table} (
                    id SERIAL PRIMARY KEY,
                    geometry geometry(MultiPolygon, 4326),
                    attributes JSONB DEFAULT '{{}}'::jsonb
                )
            """))
            self.db.commit()
            
            with fiona.open(shapefile_path) as src:
                logger.info(f"📊 Source CRS: {src.crs}")
                logger.info(f"📊 Feature count: {len(src)}")
                
                # Setup coordinate transformation if needed
                source_crs = src.crs
                target_crs = pyproj.CRS.from_epsg(4326)
                
                transformer = None
                if source_crs and source_crs != target_crs:
                    try:
                        source_proj = pyproj.CRS(source_crs)
                        transformer = pyproj.Transformer.from_crs(
                            source_proj, target_crs, always_xy=True
                        )
                        logger.info(f"🔄 Coordinate transformation: {source_proj} -> {target_crs}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not setup coordinate transformation: {e}")
                
                # Import features
                imported_count = 0
                for i, feature in enumerate(src):
                    try:
                        geom = shape(feature['geometry'])
                        
                        # Transform coordinates if needed
                        if transformer:
                            geom = transform(transformer.transform, geom)
                        
                        # Ensure MultiPolygon type
                        if geom.geom_type == 'Polygon':
                            geom = MultiPolygon([geom])
                        elif geom.geom_type != 'MultiPolygon':
                            logger.warning(f"⚠️ Skipping feature {i}: unsupported geometry type {geom.geom_type}")
                            continue
                        
                        # Validate geometry
                        if not geom.is_valid:
                            logger.warning(f"⚠️ Invalid geometry at feature {i}, attempting to fix...")
                            geom = geom.buffer(0)  # Simple fix for invalid geometries
                        
                        # Insert into temp table
                        self.db.execute(text(f"""
                            INSERT INTO {self.temp_table} (geometry, attributes)
                            VALUES (ST_GeomFromGeoJSON(:geom), :attrs::jsonb)
                        """), {
                            'geom': json.dumps(mapping(geom)),
                            'attrs': json.dumps(feature['properties'] or {})
                        })
                        
                        imported_count += 1
                        
                        if imported_count % 100 == 0:
                            logger.info(f"📈 Imported {imported_count} features...")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error processing feature {i}: {e}")
                        continue
                
                self.db.commit()
                logger.info(f"✅ Fallback import completed: {imported_count} features")
                return imported_count > 0
                
        except Exception as e:
            logger.error(f"❌ Fallback import failed: {e}")
            self.db.rollback()
            return False
    
    def process_imported_data(self, dataset_name: str, district: str, ward: str, village: str) -> int:
        """Process imported data into land_plots table with enhanced validation"""
        try:
            # Verify temp table exists and has data
            result = self.db.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = '{self.temp_table}'
            """)).scalar()
            
            if not result:
                raise Exception(f"Temporary table {self.temp_table} does not exist")
            
            # Get count and validate data
            imported_count = self.db.execute(text(f"SELECT COUNT(*) FROM {self.temp_table}")).scalar()
            logger.info(f"📊 Processing {imported_count} imported records")
            
            if imported_count == 0:
                raise Exception("No data found in temporary table")
            
            # Analyze table structure
            columns = self.db.execute(text(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = '{self.temp_table}'
                ORDER BY ordinal_position
            """)).fetchall()
            
            logger.info(f"📋 Temp table structure: {[(col[0], col[1]) for col in columns]}")
            
            # Check for attributes column (fallback method) vs individual columns (ogr2ogr)
            has_attributes_col = any(col[0] == 'attributes' for col in columns)
            
            if has_attributes_col:
                # Fallback method - data is in attributes JSONB column
                logger.info("🔄 Processing data from JSONB attributes column")
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
                            attributes->>'PLOT_NO',
                            '{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY id)::text, 4, '0')
                        ) as plot_code,
                        'available' as status,
                        COALESCE(
                            CAST(NULLIF(attributes->>'area_ha', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'AREA_HA', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'area', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'AREA', '') AS NUMERIC),
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
                      AND ST_IsValid(geometry)
                      AND ST_Area(geometry) > 0
                    ON CONFLICT (plot_code) DO NOTHING
                """
            else:
                # ogr2ogr method - data is in individual columns
                logger.info("🔄 Processing data from individual columns")
                
                # Get non-system columns
                attr_columns = [col[0] for col in columns 
                              if col[0] not in ['id', 'geometry', 'ogc_fid', 'wkb_geometry']]
                
                # Build attributes JSON from available columns
                if attr_columns:
                    json_pairs = []
                    for col in attr_columns:
                        json_pairs.append(f"'{col}', COALESCE({col}::text, '')")
                    json_build = f"jsonb_strip_nulls(jsonb_build_object({', '.join(json_pairs)}))"
                else:
                    json_build = "'{}'::jsonb"
                
                # Find potential plot code column
                plot_code_col = None
                for col in attr_columns:
                    if col.lower() in ['plot_code', 'plotcode', 'code', 'plot_no', 'plotnum', 'plot_id']:
                        plot_code_col = col
                        break
                
                plot_code_expr = (
                    f"COALESCE(NULLIF({plot_code_col}::text, ''), '{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY ogc_fid)::text, 4, '0'))"
                    if plot_code_col else
                    f"'{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY ogc_fid)::text, 4, '0')"
                )
                
                # Find area column
                area_col = None
                for col in attr_columns:
                    if col.lower() in ['area_ha', 'area', 'hectares', 'area_hect']:
                        area_col = col
                        break
                
                area_expr = (
                    f"COALESCE(CAST(NULLIF({area_col}::text, '') AS NUMERIC), ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS NUMERIC), 4))"
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
                      AND ST_IsValid(geometry)
                      AND ST_Area(geometry) > 0
                    ON CONFLICT (plot_code) DO NOTHING
                """
            
            # Execute the insert with enhanced error handling
            logger.info("💾 Inserting processed data into land_plots table...")
            result = self.db.execute(text(insert_sql), {
                'district': district,
                'ward': ward,
                'village': village,
                'dataset_name': dataset_name
            })
            
            self.db.commit()
            
            # Verify insertion
            inserted_count = self.db.execute(text("""
                SELECT COUNT(*) FROM land_plots 
                WHERE dataset_name = :dataset_name
            """), {'dataset_name': dataset_name}).scalar()
            
            logger.info(f"✅ Successfully inserted {inserted_count} land plots")
            
            # Get spatial statistics
            stats = self.db.execute(text("""
                SELECT 
                    COUNT(*) as count,
                    AVG(area_hectares) as avg_area,
                    MIN(area_hectares) as min_area,
                    MAX(area_hectares) as max_area,
                    ST_XMin(ST_Extent(geometry)) as min_lon,
                    ST_YMin(ST_Extent(geometry)) as min_lat,
                    ST_XMax(ST_Extent(geometry)) as max_lon,
                    ST_YMax(ST_Extent(geometry)) as max_lat
                FROM land_plots 
                WHERE dataset_name = :dataset_name
            """), {'dataset_name': dataset_name}).fetchone()
            
            if stats:
                logger.info(f"📊 Dataset statistics:")
                logger.info(f"   - Count: {stats.count}")
                logger.info(f"   - Area range: {stats.min_area:.4f} - {stats.max_area:.4f} hectares")
                logger.info(f"   - Average area: {stats.avg_area:.4f} hectares")
                logger.info(f"   - Spatial extent: ({stats.min_lon:.6f}, {stats.min_lat:.6f}) to ({stats.max_lon:.6f}, {stats.max_lat:.6f})")
            
            # Clean up temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            self.db.commit()
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"❌ Error processing imported data: {e}")
            self.db.rollback()
            raise
    
    def create_import_record(self, shapefile_path: str, dataset_name: str, feature_count: int):
        """Create a record of the shapefile import"""
        try:
            # Get file hashes for all shapefile components
            base_path = os.path.splitext(shapefile_path)[0]
            file_hashes = {}
            
            for ext in ['shp', 'shx', 'dbf', 'prj', 'cpg']:
                file_path = f"{base_path}.{ext}"
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        file_hashes[ext] = hashlib.sha256(content).hexdigest()
            
            # Create import record
            import_record = ShapefileImport(
                dataset_name=dataset_name,
                file_path=shapefile_path,
                file_hash=file_hashes.get('shp', ''),
                feature_count=feature_count,
                import_status='completed',
                metadata={
                    'file_hashes': file_hashes,
                    'import_method': 'ogr2ogr' if self.check_gdal_availability() else 'python_fallback',
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            self.db.add(import_record)
            self.db.commit()
            
            logger.info(f"📝 Import record created for dataset: {dataset_name}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not create import record: {e}")
    
    def import_shapefile(self, shapefile_path: str, dataset_name: str, 
                        district: str, ward: str, village: str) -> int:
        """Main import method with comprehensive error handling"""
        logger.info(f"🚀 Starting shapefile import: {shapefile_path}")
        logger.info(f"📍 Target location: {district}/{ward}/{village}")
        
        # Validate shapefile exists
        if not os.path.exists(shapefile_path):
            raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")
        
        # Get shapefile information
        info = self.get_shapefile_info(shapefile_path)
        logger.info(f"📊 Shapefile analysis: {info['feature_count']} features, {info['geometry_type']} geometry")
        
        if info['feature_count'] == 0:
            raise Exception("Shapefile contains no features")
        
        # Try ogr2ogr first, then fallback to Python
        success = self.import_with_ogr2ogr(shapefile_path)
        if not success:
            logger.info("🔄 Trying Python fallback import method...")
            success = self.import_with_fallback(shapefile_path)
        
        if not success:
            raise Exception("Both import methods failed")
        
        # Process the imported data
        inserted_count = self.process_imported_data(dataset_name, district, ward, village)
        
        # Create import record
        self.create_import_record(shapefile_path, dataset_name, inserted_count)
        
        logger.info(f"🎉 Import completed successfully: {inserted_count} plots imported")
        return inserted_count

def seed_sample_data():
    """Seed the database with sample Tanzania land plot data"""
    logger.info("🌱 Starting database seeding process...")
    
    # Database session
    db = SessionLocal()
    
    try:
        # Initialize importer
        importer = EnhancedShapefileImporter(db)
        
        # Path to sample shapefile
        shapefile_path = "/home/project/backend/data/test_mbuyuni/test_mbuyuni.shp"
        
        if not os.path.exists(shapefile_path):
            logger.error(f"❌ Sample shapefile not found: {shapefile_path}")
            
            # List available files in the directory
            data_dir = os.path.dirname(shapefile_path)
            if os.path.exists(data_dir):
                files = os.listdir(data_dir)
                logger.info(f"📁 Available files in {data_dir}: {files}")
            
            return False
        
        # Check for required shapefile components
        base_path = os.path.splitext(shapefile_path)[0]
        required_files = ['shp', 'shx', 'dbf']
        missing_files = []
        
        for ext in required_files:
            file_path = f"{base_path}.{ext}"
            if not os.path.exists(file_path):
                missing_files.append(f"{base_path}.{ext}")
        
        if missing_files:
            logger.error(f"❌ Missing required shapefile components: {missing_files}")
            return False
        
        logger.info("✅ All required shapefile components found")
        
        # Import the sample data
        inserted_count = importer.import_shapefile(
            shapefile_path=shapefile_path,
            dataset_name="test_mbuyuni",
            district="Mbuyuni",
            ward="Mbuyuni Ward",
            village="Mbuyuni Village"
        )
        
        logger.info(f"🎯 Successfully imported {inserted_count} land plots")
        
        # Verify the import with comprehensive statistics
        total_plots = db.execute(text("SELECT COUNT(*) FROM land_plots")).scalar()
        available_plots = db.execute(text("SELECT COUNT(*) FROM land_plots WHERE status = 'available'")).scalar()
        
        logger.info(f"📊 Database now contains {total_plots} total plots ({available_plots} available)")
        
        # Get detailed statistics
        stats = db.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT district) as districts,
                COUNT(DISTINCT ward) as wards,
                COUNT(DISTINCT village) as villages,
                AVG(area_hectares) as avg_area,
                SUM(area_hectares) as total_area,
                ST_XMin(ST_Extent(geometry)) as min_lon,
                ST_YMin(ST_Extent(geometry)) as min_lat,
                ST_XMax(ST_Extent(geometry)) as max_lon,
                ST_YMax(ST_Extent(geometry)) as max_lat
            FROM land_plots
        """)).fetchone()
        
        if stats:
            logger.info(f"📈 Comprehensive statistics:")
            logger.info(f"   - Total plots: {stats.total}")
            logger.info(f"   - Districts: {stats.districts}")
            logger.info(f"   - Wards: {stats.wards}")
            logger.info(f"   - Villages: {stats.villages}")
            logger.info(f"   - Average area: {stats.avg_area:.4f} hectares")
            logger.info(f"   - Total area: {stats.total_area:.4f} hectares")
            logger.info(f"   - Spatial extent: ({stats.min_lon:.6f}, {stats.min_lat:.6f}) to ({stats.max_lon:.6f}, {stats.max_lat:.6f})")
            
            # Validate coordinates are within Tanzania bounds
            tanzania_bounds = {
                'north': -0.95, 'south': -11.75,
                'east': 40.44, 'west': 29.34
            }
            
            if (tanzania_bounds['west'] <= stats.min_lon <= tanzania_bounds['east'] and
                tanzania_bounds['west'] <= stats.max_lon <= tanzania_bounds['east'] and
                tanzania_bounds['south'] <= stats.min_lat <= tanzania_bounds['north'] and
                tanzania_bounds['south'] <= stats.max_lat <= tanzania_bounds['north']):
                logger.info("✅ Coordinates are within Tanzania bounds")
            else:
                logger.warning("⚠️ Some coordinates may be outside Tanzania bounds")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def main():
    """Main function with enhanced error handling"""
    logger.info("🇹🇿 Tanzania Land Plot System - Enhanced Database Seeder")
    
    # Test database connection
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"🔗 Database connected: {version}")
            
            # Test PostGIS
            result = conn.execute(text("SELECT PostGIS_Version()"))
            postgis_version = result.fetchone()[0]
            logger.info(f"🗺️ PostGIS version: {postgis_version}")
            
            # Test spatial functions
            result = conn.execute(text("SELECT ST_AsText(ST_GeomFromText('POINT(0 0)', 4326))"))
            point_test = result.fetchone()[0]
            logger.info(f"🧪 Spatial function test: {point_test}")
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
    
    # Run seeding
    success = seed_sample_data()
    
    if success:
        logger.info("🎉 Database seeding completed successfully!")
        logger.info("🚀 You can now start the application and view the plots on the map")
        return True
    else:
        logger.error("💥 Database seeding failed!")
        logger.error("🔧 Please check the logs above for specific error details")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)