"""Shapefile import & seed script for Tanzania Land Plot Ordering MVS.

Steps performed:
1. Ensure schema exists (optionally run schema.sql).
2. Detect SRID of shapefile; if not 4326, transform to 4326.
3. Load shapefile into a temporary table using ogr2ogr (preferred path) OR fallback pure Python (shapely/fiona) if ogr2ogr not present.
4. Normalize data into land_plots table computing area in hectares (ST_Area on geography for accuracy).
5. Avoid duplicating existing plot_code entries.

Usage: python seed_import.py --shapefile data/test_mbuyuni/test_mbuyuni.shp
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import tempfile
import hashlib
from typing import Optional, Dict

from sqlalchemy import text
from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_import")

DEFAULT_INTENDED_USE = "residential"  # not used in plots but can be added to attributes

def have_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def run_sql(sql: str, params: Optional[dict] = None):
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})

def ensure_schema():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if os.path.exists(schema_path):
        logger.info("Ensuring database schema (schema.sql)...")
        with open(schema_path, "r", encoding="utf-8") as f:
            statements = f.read()
        with engine.begin() as conn:
            conn.execute(text(statements))
    else:
        logger.warning("schema.sql not found; assuming schema already exists")

def import_with_ogr2ogr(shapefile: str, tmp_table: str) -> bool:
    if not have_command("ogr2ogr"):
        return False
    # Attempt to detect layer SRID (optional) with ogrinfo
    try:
        logger.info("Importing using ogr2ogr -> %s", tmp_table)
        # -nlt MULTIPOLYGON ensures MultiPolygon type
        # -lco GEOMETRY_NAME=geom to standardize then rename later
        subprocess.check_call([
            "ogr2ogr",
            "-f", "PostgreSQL",
            f"PG:dbname={engine.url.database} host={engine.url.host} port={engine.url.port or 5432} user={engine.url.username} password={engine.url.password}",
            shapefile,
            "-nln", tmp_table,
            "-nlt", "MULTIPOLYGON",
            "-lco", "GEOMETRY_NAME=geometry",
            "-lco", "FID=ogc_fid",
            "-lco", "PRECISION=NO",
            "-t_srs", "EPSG:4326",
            "-overwrite"
        ])
        return True
    except subprocess.CalledProcessError as e:
        logger.error("ogr2ogr import failed: %s", e)
        return False

def fallback_python_import(shapefile: str, tmp_table: str):
    logger.info("Fallback Python import (fiona/shapely)")
    try:
        import fiona  # type: ignore
        from shapely.geometry import shape, mapping  # type: ignore
        from shapely.ops import transform  # type: ignore
        import pyproj  # type: ignore
    except ImportError:
        logger.error("fiona + shapely + pyproj required for fallback; install them in requirements.txt")
        raise

    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table}"))
        conn.execute(text(f"CREATE TABLE {tmp_table} (id serial primary key, attributes jsonb, geometry geometry(MultiPolygon,4326))"))

    with fiona.open(shapefile) as src:
        crs = src.crs_wkt or src.crs
        proj = None
        if crs:
            source_crs = pyproj.CRS.from_wkt(crs) if isinstance(crs, str) else pyproj.CRS(src.crs)
            target_crs = pyproj.CRS.from_epsg(4326)
            if source_crs != target_crs:
                transformer = pyproj.Transformer.from_crs(source_crs, target_crs, always_xy=True)
                proj = lambda x, y: transformer.transform(x, y)
        with engine.begin() as conn:
            for feat in src:
                geom = shape(feat["geometry"])
                if proj:
                    geom = transform(proj, geom)
                if geom.geom_type == "Polygon":
                    from shapely.geometry import MultiPolygon  # type: ignore
                    geom = MultiPolygon([geom])
                attrs = feat["properties"] or {}
                conn.execute(text(f"""
                    INSERT INTO {tmp_table}(attributes, geometry)
                    VALUES (:attrs::jsonb, ST_GeomFromGeoJSON(:geom)::geometry(MultiPolygon,4326))
                """), {"attrs": json.dumps(attrs), "geom": json.dumps(mapping(geom))})

def normalize_into_land_plots(tmp_table: str, district: str, ward: str, village: str, dataset_name: str):
    logger.info("Normalizing data into land_plots...")
    with engine.begin() as conn:
        # Detect if an 'attributes' column already exists (fallback path)
        has_attributes_col = conn.execute(text(
            """
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = :t AND column_name = 'attributes'
            """), {"t": tmp_table}).scalar() is not None

        if has_attributes_col:
            # Use existing JSONB attributes (fallback python import path)
            sample = conn.execute(text(f"SELECT attributes FROM {tmp_table} LIMIT 1")).scalar()
            attr_key = None
            if sample:
                for k in sample.keys():  # type: ignore
                    if k.lower() in ("plot_code","plotid","code","plot_no","plotnum"):
                        attr_key = k
                        break
                        base_cte = f"SELECT (CASE WHEN :attr_key IS NOT NULL THEN (attributes ->> :attr_key) ELSE 'MBY-' || LPAD(row_number() OVER (ORDER BY id)::text,4,'0') END) AS plot_code_raw, attributes, geometry FROM {tmp_table}"
                        insert_sql = f"""
                WITH src AS (
                  {base_cte}
                )
                                INSERT INTO land_plots(plot_code,status,area_hectares,district,ward,village,dataset_name,geometry,attributes)
                SELECT 
                  plot_code_raw,
                  'available',
                  ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS numeric),4) AS area_hectares,
                                    :district,:ward,:village,:dataset_name,
                  ST_Multi(ST_Force2D(geometry))::geometry(MultiPolygon,4326),
                  attributes
                FROM src s
                WHERE NOT EXISTS (SELECT 1 FROM land_plots lp WHERE lp.plot_code = s.plot_code_raw);
            """
                        conn.execute(text(insert_sql), {"attr_key": attr_key, "district": district, "ward": ward, "village": village, "dataset_name": dataset_name})
        else:
            # Build attributes JSON from scalar columns dynamically.
            cols = conn.execute(text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :t
                ORDER BY ordinal_position
                """), {"t": tmp_table}).fetchall()
            col_names = [c[0] for c in cols]
            # Identify geometry column (common names)
            geom_col = None
            for candidate in ("geometry","geom","wkb_geometry"):
                if candidate in col_names:
                    geom_col = candidate
                    break
            if not geom_col:
                raise RuntimeError("Could not detect geometry column in import table")
            exclude = {geom_col, 'ogc_fid'}
            attr_cols = [c for c in col_names if c not in exclude]

            # Candidate plot code attribute search
            attr_key = None
            for k in attr_cols:
                if k.lower() in ("plot_code","plotid","code","plot_no","plotnum"):
                    attr_key = k
                    break

            # Build jsonb_build_object(...) fragment
            if attr_cols:
                json_pairs = []
                for c in attr_cols:
                    json_pairs.append(f"'{c}', {c}")
                json_build = "jsonb_strip_nulls(jsonb_build_object(" + ",".join(json_pairs) + ")) AS attributes"
            else:
                json_build = "'{}'::jsonb AS attributes"

            # Build base select
            select_list = []
            for c in attr_cols:
                select_list.append(c)
            select_list.append(geom_col)
            base_select = f"SELECT {', '.join(select_list)}, {geom_col} AS geometry FROM {tmp_table}"  # geometry alias unify

            # Compose CTE with attributes JSON construction
            src_select_cols = []
            for c in attr_cols:
                src_select_cols.append(c)
            src_select_cols.append("geometry")
            attr_select = f"SELECT *, {json_build} FROM (SELECT {', '.join(attr_cols)} , {geom_col} AS geometry FROM {tmp_table}) raw"

            # Plot code expression
            plot_code_expr = (
                f"COALESCE({attr_key}, 'MBY-' || LPAD(row_number() OVER (ORDER BY {attr_cols[0] if attr_cols else geom_col})::text,4,'0'))"
                if attr_key else
                f"'MBY-' || LPAD(row_number() OVER (ORDER BY {attr_cols[0] if attr_cols else geom_col})::text,4,'0')"
            )

            insert_sql = f"""
                WITH src AS (
                  SELECT *, {plot_code_expr} AS plot_code_raw FROM (
                    SELECT {', '.join(attr_cols)} , {geom_col} AS geometry, {json_build}
                    FROM {tmp_table}
                  ) a
                )
                INSERT INTO land_plots(plot_code,status,area_hectares,district,ward,village,dataset_name,geometry,attributes)
                SELECT 
                  plot_code_raw,
                  'available',
                  ROUND(CAST(ST_Area(geography(geometry)) / 10000 AS numeric),4) AS area_hectares,
                  :district,:ward,:village,:dataset_name,
                  ST_Multi(ST_Force2D(geometry))::geometry(MultiPolygon,4326),
                  attributes
                FROM src s
                WHERE NOT EXISTS (SELECT 1 FROM land_plots lp WHERE lp.plot_code = s.plot_code_raw);
            """
            conn.execute(text(insert_sql), {"district": district, "ward": ward, "village": village, "dataset_name": dataset_name})

        count = conn.execute(text(
            "SELECT COUNT(*) FROM land_plots WHERE district=:district AND ward=:ward AND village=:village AND dataset_name=:dataset_name"),
            {"district": district, "ward": ward, "village": village, "dataset_name": dataset_name}).scalar()
        logger.info("Total plots in district %s / ward %s / village %s: %s", district, ward, village, count)

def seed(shapefile: str, district: str, ward: str, village: str):
    if not os.path.exists(shapefile):
        raise FileNotFoundError(shapefile)
    
    logger.info(f"Starting import of {shapefile}")
    logger.info(f"Target location: {district}/{ward}/{village}")
    
    ensure_schema()
    tmp_table = "_import_land_plots_tmp"
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table} CASCADE"))
    imported = import_with_ogr2ogr(shapefile, tmp_table)
    if not imported:
        fallback_python_import(shapefile, tmp_table)
    dataset_name = os.path.basename(os.path.splitext(shapefile)[0])
    
    logger.info(f"Normalizing data for dataset: {dataset_name}")
    normalize_into_land_plots(tmp_table, district, ward, village, dataset_name)
    
    # Collect sidecar files metadata (.prj, .dbf, .shx, .cpg)
    base_no_ext = os.path.splitext(shapefile)[0]
    sidecars = {ext: f"{base_no_ext}.{ext}" for ext in ["prj","dbf","shx","cpg","shp"]}
    prj_text = None
    cpg_text = None
    dbf_schema: Dict[str,str] = {}
    file_hashes: Dict[str,str] = {}
    for ext, path in sidecars.items():
        if os.path.exists(path):
            with open(path, 'rb') as f:
                content = f.read()
                file_hashes[ext] = hashlib.sha256(content).hexdigest()
            if ext == 'prj':
                try:
                    prj_text = content.decode('utf-8', errors='ignore')
                except Exception:
                    prj_text = None
            if ext == 'cpg':
                try:
                    cpg_text = content.decode('utf-8', errors='ignore').strip()
                except Exception:
                    cpg_text = None
    # Extract DBF schema via ogrinfo if available
    if have_command('ogrinfo') and os.path.exists(sidecars['shp']):
        try:
            out = subprocess.check_output(['ogrinfo','-so', sidecars['shp'], os.path.basename(base_no_ext)], stderr=subprocess.STDOUT).decode('utf-8', errors='ignore')
            for line in out.splitlines():
                s = line.strip()
                if not s or 'Layer name:' in s or 'Geometry:' in s or 'Feature Count:' in s:
                    continue
                if 'no version information available' in s:
                    continue  # skip noisy library lines
                if ':' in s and '(' in s:
                    fname, rest = s.split(':',1)
                    fname = fname.strip()
                    rest = rest.strip()
                    if '(' in rest:
                        ftype = rest.split('(')[0].strip()
                        if fname and ftype and fname.lower() not in ('extent','fid'):
                            dbf_schema[fname] = ftype
        except Exception as e:
            logger.debug(f"ogrinfo schema parse skipped: {e}")
    # Compute feature count & bbox from inserted records for dataset
    with engine.begin() as conn:
        stats = conn.execute(text("""
            SELECT COUNT(*) AS cnt, ST_Extent(geometry) AS extent FROM land_plots 
            WHERE district=:district AND ward=:ward AND village=:village
        """), {"district": district, "ward": ward, "village": village}).fetchone()
        bbox_wkt = None
        if stats.extent:
            # extent returns BOX(minx miny,maxx maxy)
            box_vals = stats.extent.replace('BOX(','').replace(')','').split(',')
            minx,miny = map(float, box_vals[0].split())
            maxx,maxy = map(float, box_vals[1].split())
            bbox_wkt = f"POLYGON(({minx} {miny},{maxx} {miny},{maxx} {maxy},{minx} {maxy},{minx} {miny}))"
        # Upsert metadata
        conn.execute(text("""
            INSERT INTO shapefile_imports(dataset_name, prj, cpg, dbf_schema, file_hashes, feature_count, bbox)
            VALUES (:dataset_name, :prj, :cpg, CAST(:dbf_schema AS jsonb), CAST(:file_hashes AS jsonb), :cnt,
                CASE WHEN :bbox_wkt IS NOT NULL THEN ST_GeomFromText(:bbox_wkt,4326) ELSE NULL END)
            ON CONFLICT (dataset_name) DO UPDATE SET
              prj = EXCLUDED.prj,
              cpg = EXCLUDED.cpg,
              dbf_schema = EXCLUDED.dbf_schema,
              file_hashes = EXCLUDED.file_hashes,
              feature_count = EXCLUDED.feature_count,
              bbox = EXCLUDED.bbox,
              imported_at = now();
        """), {
            "dataset_name": dataset_name,
            "prj": prj_text,
            "cpg": cpg_text,
            "dbf_schema": json.dumps(dbf_schema),
            "file_hashes": json.dumps(file_hashes),
            "cnt": stats.cnt or 0,
            "bbox_wkt": bbox_wkt
        })
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {tmp_table} CASCADE"))
    
    # Final verification
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) as count, 
                   ST_XMin(ST_Extent(geometry)) as min_lon,
                   ST_YMin(ST_Extent(geometry)) as min_lat,
                   ST_XMax(ST_Extent(geometry)) as max_lon,
                   ST_YMax(ST_Extent(geometry)) as max_lat
            FROM land_plots 
            WHERE dataset_name = :dataset_name
        """), {"dataset_name": dataset_name})
        stats = result.fetchone()
        
        logger.info(f"Import completed successfully!")
        logger.info(f"Imported {stats.count} plots")
        logger.info(f"Spatial extent: ({stats.min_lon:.6f}, {stats.min_lat:.6f}) to ({stats.max_lon:.6f}, {stats.max_lat:.6f})")
        
        if stats.count == 0:
            logger.error("No plots were imported! Check the shapefile and import process.")
        elif not (29 <= stats.min_lon <= 41 and -12 <= stats.min_lat <= -1):
            logger.warning("Imported coordinates may be outside Tanzania bounds")
        else:
            logger.info("✅ Import validation successful")

def main():
    parser = argparse.ArgumentParser(description="Seed land plots from Tanzanian shapefile")
    parser.add_argument("--shapefile", required=True, help="Path to .shp file")
    parser.add_argument("--district", default="MbuyuniDistrict")
    parser.add_argument("--ward", default="MbuyuniWard")
    parser.add_argument("--village", default="MbuyuniVillage")
    args = parser.parse_args()
    seed(args.shapefile, args.district, args.ward, args.village)

if __name__ == "__main__":
    main()
