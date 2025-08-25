#!/usr/bin/env python3
"""
Enhanced Comprehensive Shapefile Processing System for Tanzania Land Plots
Handles all shapefile components with robust error handling and validation
"""

import os
import sys
import json
import logging
import hashlib
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import uuid

from sqlalchemy import create_engine, text, MetaData, Table, Column, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from geoalchemy2 import Geometry

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('shapefile_processing.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/tanzania_land_plots"
)

# Handle Railway/Render PostgreSQL URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create enhanced engine with optimized settings
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
    connect_args={
        "options": "-c timezone=UTC",
        "application_name": "tanzania_shapefile_processor"
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tanzania geographic bounds for validation
TANZANIA_BOUNDS = {
    'north': -0.95,
    'south': -11.75,
    'east': 40.44,
    'west': 29.34
}

class EnhancedShapefileProcessor:
    """
    Comprehensive shapefile processing system with enhanced error handling,
    validation, and support for large datasets
    """
    
    def __init__(self, db_session):
        self.db = db_session
        self.temp_table = f"temp_shapefile_import_{uuid.uuid4().hex[:8]}"
        self.processed_features = 0
        self.validation_errors = []
        self.import_metadata = {}
        
    def validate_shapefile_components(self, shapefile_path: str) -> Dict[str, Any]:
        """
        Comprehensive validation of all shapefile components
        """
        logger.info(f"🔍 Validating shapefile components for: {shapefile_path}")
        
        base_path = os.path.splitext(shapefile_path)[0]
        components = {
            'shp': f"{base_path}.shp",    # Main geometry file
            'shx': f"{base_path}.shx",    # Shape index file
            'dbf': f"{base_path}.dbf",    # Attribute data file
            'prj': f"{base_path}.prj",    # Projection information
            'cpg': f"{base_path}.cpg"     # Code page file
        }
        
        validation_result = {
            'valid': True,
            'components': {},
            'missing_required': [],
            'file_sizes': {},
            'total_size': 0,
            'encoding': None,
            'projection': None
        }
        
        # Required components
        required = ['shp', 'shx', 'dbf']
        
        for component, file_path in components.items():
            exists = os.path.exists(file_path)
            size = os.path.getsize(file_path) if exists else 0
            
            validation_result['components'][component] = {
                'exists': exists,
                'path': file_path,
                'size': size,
                'readable': False
            }
            
            if exists:
                try:
                    with open(file_path, 'rb') as f:
                        f.read(1)  # Test readability
                    validation_result['components'][component]['readable'] = True
                    validation_result['file_sizes'][component] = size
                    validation_result['total_size'] += size
                except Exception as e:
                    logger.warning(f"⚠️ Cannot read {component} file: {e}")
                    validation_result['valid'] = False
            
            if component in required and not exists:
                validation_result['missing_required'].append(component)
                validation_result['valid'] = False
        
        # Extract encoding information from CPG file
        if validation_result['components']['cpg']['exists']:
            try:
                with open(components['cpg'], 'r', encoding='utf-8') as f:
                    validation_result['encoding'] = f.read().strip()
                logger.info(f"📝 Detected encoding: {validation_result['encoding']}")
            except Exception as e:
                logger.warning(f"⚠️ Could not read CPG file: {e}")
        
        # Extract projection information from PRJ file
        if validation_result['components']['prj']['exists']:
            try:
                with open(components['prj'], 'r', encoding='utf-8') as f:
                    validation_result['projection'] = f.read().strip()
                logger.info(f"🗺️ Detected projection: {validation_result['projection'][:100]}...")
            except Exception as e:
                logger.warning(f"⚠️ Could not read PRJ file: {e}")
        
        # Log validation summary
        logger.info(f"📊 Validation Summary:")
        logger.info(f"   - Valid: {validation_result['valid']}")
        logger.info(f"   - Total size: {validation_result['total_size'] / 1024 / 1024:.2f} MB")
        logger.info(f"   - Missing required: {validation_result['missing_required']}")
        
        return validation_result
    
    def check_gdal_availability(self) -> Dict[str, Any]:
        """
        Enhanced GDAL availability check with version information
        """
        gdal_info = {
            'available': False,
            'version': None,
            'supported_formats': [],
            'error': None
        }
        
        try:
            # Check ogr2ogr
            result = subprocess.run(['ogr2ogr', '--version'], 
                                  capture_output=True, check=True, text=True, timeout=10)
            gdal_info['version'] = result.stdout.strip()
            gdal_info['available'] = True
            
            # Check supported formats
            formats_result = subprocess.run(['ogr2ogr', '--formats'], 
                                          capture_output=True, text=True, timeout=10)
            if formats_result.returncode == 0:
                gdal_info['supported_formats'] = formats_result.stdout.split('\n')[:10]  # First 10 formats
            
            logger.info(f"✅ GDAL available: {gdal_info['version']}")
            
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            gdal_info['error'] = str(e)
            logger.warning(f"⚠️ GDAL not available: {e}")
        
        return gdal_info
    
    def get_shapefile_metadata(self, shapefile_path: str) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from shapefile using ogrinfo
        """
        metadata = {
            'feature_count': 0,
            'geometry_type': None,
            'spatial_extent': None,
            'coordinate_system': None,
            'fields': [],
            'layer_name': None
        }
        
        try:
            # Get basic info
            result = subprocess.run([
                'ogrinfo', '-so', '-al', shapefile_path
            ], capture_output=True, text=True, check=True, timeout=30)
            
            output = result.stdout
            logger.info("📋 Extracting shapefile metadata...")
            
            # Parse output
            for line in output.split('\n'):
                line = line.strip()
                
                if 'Layer name:' in line:
                    metadata['layer_name'] = line.split('Layer name:')[1].strip()
                elif 'Feature Count:' in line:
                    try:
                        metadata['feature_count'] = int(line.split(':')[1].strip())
                    except ValueError:
                        pass
                elif 'Geometry:' in line:
                    metadata['geometry_type'] = line.split('Geometry:')[1].strip()
                elif 'Extent:' in line:
                    try:
                        extent_str = line.split('Extent:')[1].strip()
                        # Parse extent: (minx, miny) - (maxx, maxy)
                        coords = extent_str.replace('(', '').replace(')', '').replace(' - ', ',').split(',')
                        if len(coords) == 4:
                            metadata['spatial_extent'] = {
                                'minx': float(coords[0].strip()),
                                'miny': float(coords[1].strip()),
                                'maxx': float(coords[2].strip()),
                                'maxy': float(coords[3].strip())
                            }
                    except (ValueError, IndexError):
                        pass
                elif ':' in line and '(' in line and ')' in line and not line.startswith('Layer'):
                    # Parse field definitions
                    try:
                        field_name = line.split(':')[0].strip()
                        field_info = line.split(':')[1].strip()
                        field_type = field_info.split('(')[0].strip()
                        
                        if field_name and field_type and field_name.lower() not in ['extent', 'fid']:
                            metadata['fields'].append({
                                'name': field_name,
                                'type': field_type,
                                'info': field_info
                            })
                    except (ValueError, IndexError):
                        pass
            
            logger.info(f"📊 Metadata extracted: {metadata['feature_count']} features, {len(metadata['fields'])} fields")
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning(f"⚠️ Could not extract metadata: {e}")
        
        return metadata
    
    def import_with_ogr2ogr(self, shapefile_path: str, validation_result: Dict) -> bool:
        """
        Enhanced ogr2ogr import with comprehensive error handling and optimization
        """
        logger.info("🔄 Starting ogr2ogr import process...")
        
        try:
            # Build PostgreSQL connection string
            db_url = engine.url
            pg_conn = (f"PG:host={db_url.host} port={db_url.port or 5432} "
                      f"dbname={db_url.database} user={db_url.username} "
                      f"password={db_url.password}")
            
            # Drop existing temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            self.db.commit()
            
            # Build enhanced ogr2ogr command
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
                '--config', 'GDAL_HTTP_TIMEOUT', '30',
                '--config', 'OGR_TRUNCATE', 'YES'
            ]
            
            # Add encoding if detected
            if validation_result.get('encoding'):
                cmd.extend(['--config', 'SHAPE_ENCODING', validation_result['encoding']])
            
            # Add source SRS if detected
            if validation_result.get('projection'):
                # Try to detect common Tanzania projections
                if 'UTM_Zone_37S' in validation_result['projection']:
                    cmd.extend(['-s_srs', 'EPSG:32737'])  # WGS 84 / UTM zone 37S
                elif 'UTM_Zone_36S' in validation_result['projection']:
                    cmd.extend(['-s_srs', 'EPSG:32736'])  # WGS 84 / UTM zone 36S
                elif 'Arc_1960' in validation_result['projection']:
                    if 'UTM_Zone_37S' in validation_result['projection']:
                        cmd.extend(['-s_srs', 'EPSG:21097'])  # Arc 1960 / UTM zone 37S
                    elif 'UTM_Zone_36S' in validation_result['projection']:
                        cmd.extend(['-s_srs', 'EPSG:21096'])  # Arc 1960 / UTM zone 36S
            
            logger.info("🚀 Executing ogr2ogr command...")
            logger.info(f"Command: {' '.join(cmd[:8])} ... [connection details hidden]")
            
            # Execute with timeout and progress monitoring
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            try:
                stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
                
                if process.returncode == 0:
                    logger.info("✅ ogr2ogr import completed successfully")
                    
                    # Verify import
                    count = self.db.execute(text(f"SELECT COUNT(*) FROM {self.temp_table}")).scalar()
                    logger.info(f"📊 Imported {count} features to temporary table")
                    
                    if count == 0:
                        logger.warning("⚠️ No features imported - empty result")
                        return False
                    
                    return True
                else:
                    logger.error(f"❌ ogr2ogr failed with return code {process.returncode}")
                    logger.error(f"stderr: {stderr}")
                    return False
                    
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error("❌ ogr2ogr import timed out after 5 minutes")
                return False
                
        except Exception as e:
            logger.error(f"❌ ogr2ogr import failed: {e}")
            return False
    
    def import_with_python_fallback(self, shapefile_path: str, validation_result: Dict) -> bool:
        """
        Enhanced Python fallback import using fiona and shapely
        """
        logger.info("🐍 Starting Python fallback import...")
        
        try:
            import fiona
            from shapely.geometry import shape, mapping, MultiPolygon
            from shapely.ops import transform
            import pyproj
        except ImportError as e:
            logger.error(f"❌ Required libraries not available: {e}")
            logger.error("Install with: pip install fiona shapely pyproj")
            return False
        
        try:
            # Drop existing temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            
            # Create temp table with enhanced structure
            self.db.execute(text(f"""
                CREATE TABLE {self.temp_table} (
                    id SERIAL PRIMARY KEY,
                    geometry geometry(MultiPolygon, 4326),
                    attributes JSONB DEFAULT '{{}}'::jsonb,
                    original_fid INTEGER,
                    import_timestamp TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            self.db.commit()
            
            # Open shapefile with encoding detection
            encoding = validation_result.get('encoding', 'utf-8')
            
            with fiona.open(shapefile_path, encoding=encoding) as src:
                logger.info(f"📊 Source info:")
                logger.info(f"   - CRS: {src.crs}")
                logger.info(f"   - Feature count: {len(src)}")
                logger.info(f"   - Schema: {src.schema}")
                
                # Setup coordinate transformation
                source_crs = src.crs
                target_crs = pyproj.CRS.from_epsg(4326)
                
                transformer = None
                if source_crs and source_crs != target_crs:
                    try:
                        if isinstance(source_crs, dict):
                            source_proj = pyproj.CRS.from_dict(source_crs)
                        else:
                            source_proj = pyproj.CRS(source_crs)
                        
                        transformer = pyproj.Transformer.from_crs(
                            source_proj, target_crs, always_xy=True
                        )
                        logger.info(f"🔄 Coordinate transformation: {source_proj} -> {target_crs}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not setup coordinate transformation: {e}")
                
                # Process features in batches for better performance
                batch_size = 100
                batch = []
                imported_count = 0
                error_count = 0
                
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
                            error_count += 1
                            continue
                        
                        # Validate geometry
                        if not geom.is_valid:
                            logger.warning(f"⚠️ Invalid geometry at feature {i}, attempting to fix...")
                            geom = geom.buffer(0)  # Simple fix for invalid geometries
                            if not geom.is_valid:
                                logger.warning(f"⚠️ Could not fix geometry at feature {i}, skipping")
                                error_count += 1
                                continue
                        
                        # Validate coordinates are within Tanzania bounds
                        bounds = geom.bounds
                        if not (TANZANIA_BOUNDS['west'] <= bounds[0] <= TANZANIA_BOUNDS['east'] and
                                TANZANIA_BOUNDS['west'] <= bounds[2] <= TANZANIA_BOUNDS['east'] and
                                TANZANIA_BOUNDS['south'] <= bounds[1] <= TANZANIA_BOUNDS['north'] and
                                TANZANIA_BOUNDS['south'] <= bounds[3] <= TANZANIA_BOUNDS['north']):
                            logger.warning(f"⚠️ Feature {i} coordinates outside Tanzania bounds: {bounds}")
                            # Don't skip, just warn - might be edge case
                        
                        # Prepare batch insert
                        batch.append({
                            'geom': json.dumps(mapping(geom)),
                            'attrs': json.dumps(feature['properties'] or {}),
                            'fid': i
                        })
                        
                        # Execute batch insert
                        if len(batch) >= batch_size:
                            self._execute_batch_insert(batch)
                            imported_count += len(batch)
                            batch = []
                            
                            if imported_count % 500 == 0:
                                logger.info(f"📈 Imported {imported_count} features...")
                    
                    except Exception as e:
                        logger.warning(f"⚠️ Error processing feature {i}: {e}")
                        error_count += 1
                        continue
                
                # Insert remaining batch
                if batch:
                    self._execute_batch_insert(batch)
                    imported_count += len(batch)
                
                self.db.commit()
                
                logger.info(f"✅ Python fallback import completed:")
                logger.info(f"   - Imported: {imported_count} features")
                logger.info(f"   - Errors: {error_count} features")
                
                return imported_count > 0
                
        except Exception as e:
            logger.error(f"❌ Python fallback import failed: {e}")
            self.db.rollback()
            return False
    
    def _execute_batch_insert(self, batch: List[Dict]):
        """Execute batch insert for better performance"""
        if not batch:
            return
        
        values = []
        for item in batch:
            values.append(f"(ST_GeomFromGeoJSON('{item['geom']}')::geometry(MultiPolygon,4326), "
                         f"'{item['attrs']}'::jsonb, {item['fid']})")
        
        sql = f"""
            INSERT INTO {self.temp_table} (geometry, attributes, original_fid)
            VALUES {', '.join(values)}
        """
        
        self.db.execute(text(sql))
    
    def process_imported_data(self, dataset_name: str, district: str, ward: str, village: str) -> int:
        """
        Enhanced data processing with comprehensive validation and optimization
        """
        logger.info("💾 Processing imported data into land_plots table...")
        
        try:
            # Verify temp table exists and has data
            table_exists = self.db.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = '{self.temp_table}'
            """)).scalar()
            
            if not table_exists:
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
            
            # Check for attributes column (Python method) vs individual columns (ogr2ogr)
            has_attributes_col = any(col[0] == 'attributes' for col in columns)
            
            if has_attributes_col:
                # Python method - data is in attributes JSONB column
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
                            attributes->>'PLOTNUM',
                            '{dataset_name}_' || LPAD(ROW_NUMBER() OVER (ORDER BY id)::text, 4, '0')
                        ) as plot_code,
                        'available' as status,
                        COALESCE(
                            CAST(NULLIF(attributes->>'area_ha', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'AREA_HA', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'area', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'AREA', '') AS NUMERIC),
                            CAST(NULLIF(attributes->>'hectares', '') AS NUMERIC),
                            ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS NUMERIC), 4)
                        ) as area_hectares,
                        :district as district,
                        :ward as ward,
                        :village as village,
                        :dataset_name as dataset_name,
                        ST_Multi(ST_Force2D(geometry))::geometry(MultiPolygon,4326) as geometry,
                        attributes || jsonb_build_object(
                            'import_method', 'python_fallback',
                            'import_timestamp', NOW(),
                            'original_fid', original_fid
                        ) as attributes,
                        NOW() as created_at,
                        NOW() as updated_at
                    FROM {self.temp_table}
                    WHERE geometry IS NOT NULL
                      AND ST_IsValid(geometry)
                      AND ST_Area(geometry) > 0
                    ON CONFLICT (plot_code) DO UPDATE SET
                        updated_at = NOW(),
                        attributes = EXCLUDED.attributes
                """
            else:
                # ogr2ogr method - data is in individual columns
                logger.info("🔄 Processing data from individual columns")
                
                # Get non-system columns
                attr_columns = [col[0] for col in columns 
                              if col[0] not in ['id', 'geometry', 'ogc_fid', 'wkb_geometry', 'import_timestamp']]
                
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
                    if col.lower() in ['area_ha', 'area', 'hectares', 'area_hect', 'area_m2']:
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
                        {json_build} || jsonb_build_object(
                            'import_method', 'ogr2ogr',
                            'import_timestamp', NOW()
                        ) as attributes,
                        NOW() as created_at,
                        NOW() as updated_at
                    FROM {self.temp_table}
                    WHERE geometry IS NOT NULL
                      AND ST_IsValid(geometry)
                      AND ST_Area(geometry) > 0
                    ON CONFLICT (plot_code) DO UPDATE SET
                        updated_at = NOW(),
                        attributes = EXCLUDED.attributes
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
            
            logger.info(f"✅ Successfully processed {inserted_count} land plots")
            
            # Get comprehensive statistics
            stats = self.db.execute(text("""
                SELECT 
                    COUNT(*) as count,
                    AVG(area_hectares) as avg_area,
                    MIN(area_hectares) as min_area,
                    MAX(area_hectares) as max_area,
                    SUM(area_hectares) as total_area,
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
                logger.info(f"   - Total area: {stats.total_area:.4f} hectares")
                logger.info(f"   - Spatial extent: ({stats.min_lon:.6f}, {stats.min_lat:.6f}) to ({stats.max_lon:.6f}, {stats.max_lat:.6f})")
                
                # Validate coordinates are within Tanzania bounds
                if (TANZANIA_BOUNDS['west'] <= stats.min_lon <= TANZANIA_BOUNDS['east'] and
                    TANZANIA_BOUNDS['west'] <= stats.max_lon <= TANZANIA_BOUNDS['east'] and
                    TANZANIA_BOUNDS['south'] <= stats.min_lat <= TANZANIA_BOUNDS['north'] and
                    TANZANIA_BOUNDS['south'] <= stats.max_lat <= TANZANIA_BOUNDS['north']):
                    logger.info("✅ All coordinates are within Tanzania bounds")
                else:
                    logger.warning("⚠️ Some coordinates may be outside Tanzania bounds")
            
            # Clean up temp table
            self.db.execute(text(f"DROP TABLE IF EXISTS {self.temp_table} CASCADE"))
            self.db.commit()
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"❌ Error processing imported data: {e}")
            self.db.rollback()
            raise
    
    def create_import_record(self, shapefile_path: str, dataset_name: str, 
                           validation_result: Dict, metadata: Dict, feature_count: int):
        """
        Create comprehensive import record with all metadata
        """
        try:
            # Calculate file hashes for all components
            base_path = os.path.splitext(shapefile_path)[0]
            file_hashes = {}
            
            for ext in ['shp', 'shx', 'dbf', 'prj', 'cpg']:
                file_path = f"{base_path}.{ext}"
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        file_hashes[ext] = hashlib.sha256(content).hexdigest()
            
            # Create comprehensive import record
            import_data = {
                'dataset_name': dataset_name,
                'prj': validation_result.get('projection'),
                'cpg': validation_result.get('encoding'),
                'dbf_schema': {field['name']: field['type'] for field in metadata.get('fields', [])},
                'file_hashes': file_hashes,
                'feature_count': feature_count,
                'bbox': None
            }
            
            # Create bounding box if spatial extent is available
            if metadata.get('spatial_extent'):
                extent = metadata['spatial_extent']
                bbox_wkt = (f"POLYGON(({extent['minx']} {extent['miny']},"
                           f"{extent['maxx']} {extent['miny']},"
                           f"{extent['maxx']} {extent['maxy']},"
                           f"{extent['minx']} {extent['maxy']},"
                           f"{extent['minx']} {extent['miny']}))")
                import_data['bbox'] = bbox_wkt
            
            # Insert or update import record
            self.db.execute(text("""
                INSERT INTO shapefile_imports(
                    dataset_name, prj, cpg, dbf_schema, file_hashes, feature_count, bbox
                )
                VALUES (
                    :dataset_name, :prj, :cpg, 
                    CAST(:dbf_schema AS jsonb), CAST(:file_hashes AS jsonb), 
                    :feature_count,
                    CASE WHEN :bbox IS NOT NULL THEN ST_GeomFromText(:bbox, 4326) ELSE NULL END
                )
                ON CONFLICT (dataset_name) DO UPDATE SET
                    prj = EXCLUDED.prj,
                    cpg = EXCLUDED.cpg,
                    dbf_schema = EXCLUDED.dbf_schema,
                    file_hashes = EXCLUDED.file_hashes,
                    feature_count = EXCLUDED.feature_count,
                    bbox = EXCLUDED.bbox,
                    imported_at = NOW()
            """), {
                'dataset_name': dataset_name,
                'prj': import_data['prj'],
                'cpg': import_data['cpg'],
                'dbf_schema': json.dumps(import_data['dbf_schema']),
                'file_hashes': json.dumps(import_data['file_hashes']),
                'feature_count': feature_count,
                'bbox': import_data['bbox']
            })
            
            self.db.commit()
            logger.info(f"📝 Import record created for dataset: {dataset_name}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not create import record: {e}")
    
    def process_shapefile(self, shapefile_path: str, dataset_name: str, 
                         district: str, ward: str, village: str) -> int:
        """
        Main comprehensive shapefile processing method
        """
        logger.info(f"🚀 Starting comprehensive shapefile processing: {shapefile_path}")
        logger.info(f"📍 Target location: {district}/{ward}/{village}")
        logger.info(f"🏷️ Dataset name: {dataset_name}")
        
        # Step 1: Validate shapefile components
        validation_result = self.validate_shapefile_components(shapefile_path)
        if not validation_result['valid']:
            raise Exception(f"Shapefile validation failed: {validation_result['missing_required']}")
        
        # Step 2: Check GDAL availability
        gdal_info = self.check_gdal_availability()
        
        # Step 3: Extract metadata
        metadata = {}
        if gdal_info['available']:
            metadata = self.get_shapefile_metadata(shapefile_path)
        
        # Step 4: Import shapefile data
        success = False
        if gdal_info['available']:
            success = self.import_with_ogr2ogr(shapefile_path, validation_result)
        
        if not success:
            logger.info("🔄 Trying Python fallback import method...")
            success = self.import_with_python_fallback(shapefile_path, validation_result)
        
        if not success:
            raise Exception("Both ogr2ogr and Python fallback import methods failed")
        
        # Step 5: Process the imported data
        inserted_count = self.process_imported_data(dataset_name, district, ward, village)
        
        # Step 6: Create import record
        self.create_import_record(shapefile_path, dataset_name, validation_result, metadata, inserted_count)
        
        logger.info(f"🎉 Shapefile processing completed successfully: {inserted_count} plots imported")
        return inserted_count

def ensure_database_schema():
    """
    Ensure database schema exists with all required tables and indexes
    """
    logger.info("🔧 Ensuring database schema...")
    
    try:
        with engine.begin() as conn:
            # Enable extensions
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
            
            # Create land_plots table if not exists
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS land_plots (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    plot_code text UNIQUE NOT NULL,
                    status text NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'taken', 'pending')),
                    area_hectares numeric(12,4) NOT NULL CHECK (area_hectares > 0),
                    district text NOT NULL,
                    ward text NOT NULL,
                    village text NOT NULL,
                    dataset_name text,
                    geometry geometry(MultiPolygon,4326) NOT NULL,
                    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """))
            
            # Create plot_orders table if not exists
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS plot_orders (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    plot_id uuid NOT NULL REFERENCES land_plots(id) ON DELETE CASCADE,
                    customer_name text NOT NULL,
                    customer_phone text NOT NULL,
                    customer_email text,
                    customer_id_number text NOT NULL,
                    intended_use text NOT NULL CHECK (intended_use IN ('residential','commercial','agricultural','industrial','mixed')),
                    notes text,
                    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """))
            
            # Create shapefile_imports table if not exists
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shapefile_imports (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_name text NOT NULL UNIQUE,
                    prj text,
                    cpg text,
                    dbf_schema jsonb,
                    file_hashes jsonb,
                    feature_count integer,
                    bbox geometry(Polygon,4326),
                    imported_at timestamptz NOT NULL DEFAULT now()
                )
            """))
            
            # Create indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_land_plots_geometry ON land_plots USING GIST (geometry)",
                "CREATE INDEX IF NOT EXISTS idx_land_plots_status ON land_plots(status)",
                "CREATE INDEX IF NOT EXISTS idx_land_plots_district ON land_plots(lower(district))",
                "CREATE INDEX IF NOT EXISTS idx_land_plots_ward ON land_plots(lower(ward))",
                "CREATE INDEX IF NOT EXISTS idx_land_plots_village ON land_plots(lower(village))",
                "CREATE INDEX IF NOT EXISTS idx_land_plots_dataset ON land_plots(dataset_name)",
                "CREATE INDEX IF NOT EXISTS idx_plot_orders_plot_id ON plot_orders(plot_id)",
                "CREATE INDEX IF NOT EXISTS idx_plot_orders_status ON plot_orders(status)",
                "CREATE INDEX IF NOT EXISTS idx_shapefile_imports_bbox ON shapefile_imports USING GIST (bbox)"
            ]
            
            for index_sql in indexes:
                conn.execute(text(index_sql))
            
            logger.info("✅ Database schema ensured successfully")
            
    except Exception as e:
        logger.error(f"❌ Error ensuring database schema: {e}")
        raise

def main():
    """
    Main function to process the test_mbuyuni shapefile
    """
    logger.info("🇹🇿 Tanzania Land Plot System - Enhanced Shapefile Processor")
    
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
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
    
    # Ensure database schema
    ensure_database_schema()
    
    # Process the test_mbuyuni shapefile
    db = SessionLocal()
    
    try:
        processor = EnhancedShapefileProcessor(db)
        
        # Path to the test shapefile
        shapefile_path = "/home/project/backend/data/test_mbuyuni/test_mbuyuni.shp"
        
        if not os.path.exists(shapefile_path):
            logger.error(f"❌ Shapefile not found: {shapefile_path}")
            
            # List available files
            data_dir = os.path.dirname(shapefile_path)
            if os.path.exists(data_dir):
                files = os.listdir(data_dir)
                logger.info(f"📁 Available files in {data_dir}: {files}")
            
            return False
        
        # Process the shapefile
        inserted_count = processor.process_shapefile(
            shapefile_path=shapefile_path,
            dataset_name="test_mbuyuni",
            district="Mbuyuni",
            ward="Mbuyuni Ward",
            village="Mbuyuni Village"
        )
        
        logger.info(f"🎯 Successfully processed {inserted_count} land plots")
        
        # Verify the final result
        total_plots = db.execute(text("SELECT COUNT(*) FROM land_plots")).scalar()
        available_plots = db.execute(text("SELECT COUNT(*) FROM land_plots WHERE status = 'available'")).scalar()
        
        logger.info(f"📊 Database now contains {total_plots} total plots ({available_plots} available)")
        
        # Get comprehensive final statistics
        stats = db.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT district) as districts,
                COUNT(DISTINCT ward) as wards,
                COUNT(DISTINCT village) as villages,
                COUNT(DISTINCT dataset_name) as datasets,
                AVG(area_hectares) as avg_area,
                SUM(area_hectares) as total_area,
                ST_XMin(ST_Extent(geometry)) as min_lon,
                ST_YMin(ST_Extent(geometry)) as min_lat,
                ST_XMax(ST_Extent(geometry)) as max_lon,
                ST_YMax(ST_Extent(geometry)) as max_lat
            FROM land_plots
        """)).fetchone()
        
        if stats:
            logger.info(f"📈 Final system statistics:")
            logger.info(f"   - Total plots: {stats.total}")
            logger.info(f"   - Districts: {stats.districts}")
            logger.info(f"   - Wards: {stats.wards}")
            logger.info(f"   - Villages: {stats.villages}")
            logger.info(f"   - Datasets: {stats.datasets}")
            logger.info(f"   - Average area: {stats.avg_area:.4f} hectares")
            logger.info(f"   - Total area: {stats.total_area:.4f} hectares")
            logger.info(f"   - Spatial extent: ({stats.min_lon:.6f}, {stats.min_lat:.6f}) to ({stats.max_lon:.6f}, {stats.max_lat:.6f})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Shapefile processing failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)