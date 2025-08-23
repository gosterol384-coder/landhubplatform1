from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_
from models import LandPlot, PlotOrder
from typing import Optional, Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)

class PlotService:
    
    def get_all_plots_geojson(self, db: Session) -> Dict[str, Any]:
        """Get all plots as GeoJSON FeatureCollection"""
        try:
            logger.info("Fetching all plots as GeoJSON")
            # Query plots with geometry as GeoJSON
            query = text("""
                SELECT 
                    id::text,
                    plot_code,
                    status,
                    area_hectares,
                    district,
                    ward,
                    village,
                    attributes,
                    created_at,
                    updated_at,
                    ST_AsGeoJSON(geometry)::json as geometry
                FROM land_plots
                ORDER BY plot_code
            """)
            
            result = db.execute(query)
            plots = result.fetchall()
            
            logger.info(f"Found {len(plots)} plots in database")
            
            features = []
            for plot in plots:
                # Validate geometry
                if not plot.geometry:
                    logger.warning(f"Plot {plot.plot_code} has no geometry, skipping")
                    continue
                    
                feature = {
                    "type": "Feature",
                    "properties": {
                        "id": plot.id,
                        "plot_code": plot.plot_code,
                        "status": plot.status,
                        "area_hectares": float(plot.area_hectares),
                        "district": plot.district,
                        "ward": plot.ward,
                        "village": plot.village,
                        "attributes": plot.attributes or {},
                        "created_at": plot.created_at.isoformat() + "Z",
                        "updated_at": plot.updated_at.isoformat() + "Z"
                    },
                    "geometry": plot.geometry
                }
                features.append(feature)
            
            logger.info(f"Returning {len(features)} valid plot features")
            return {
                "type": "FeatureCollection",
                "features": features
            }
            
        except Exception as e:
            logger.error(f"Error fetching plots as GeoJSON: {e}")
            raise
    
    def get_plot_geojson(self, db: Session, plot_id: str) -> Optional[Dict[str, Any]]:
        """Get single plot as GeoJSON Feature"""
        try:
            query = text("""
                SELECT 
                    id::text,
                    plot_code,
                    status,
                    area_hectares,
                    district,
                    ward,
                    village,
                    attributes,
                    created_at,
                    updated_at,
                    ST_AsGeoJSON(geometry)::json as geometry
                FROM land_plots
                WHERE id = :plot_id
            """)
            
            result = db.execute(query, {"plot_id": plot_id})
            plot = result.fetchone()
            
            if not plot:
                return None
            
            return {
                "type": "Feature",
                "properties": {
                    "id": plot.id,
                    "plot_code": plot.plot_code,
                    "status": plot.status,
                    "area_hectares": float(plot.area_hectares),
                    "district": plot.district,
                    "ward": plot.ward,
                    "village": plot.village,
                    "attributes": plot.attributes or {},
                    "created_at": plot.created_at.isoformat() + "Z",
                    "updated_at": plot.updated_at.isoformat() + "Z"
                },
                "geometry": plot.geometry
            }
            
        except Exception as e:
            logger.error(f"Error fetching plot {plot_id} as GeoJSON: {e}")
            raise
    
    def get_plot_by_id(self, db: Session, plot_id: str) -> Optional[LandPlot]:
        """Get plot by ID"""
        try:
            return db.query(LandPlot).filter(LandPlot.id == plot_id).first()
        except Exception as e:
            logger.error(f"Error fetching plot {plot_id}: {e}")
            raise
    
    def search_plots(
        self,
        db: Session,
        district: Optional[str] = None,
        ward: Optional[str] = None,
        village: Optional[str] = None,
        status: Optional[str] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        bbox: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search plots with various filters"""
        try:
            # Build WHERE conditions
            conditions = []
            params = {}
            
            if district:
                conditions.append("LOWER(district) = LOWER(:district)")
                params["district"] = district
            
            if ward:
                conditions.append("LOWER(ward) = LOWER(:ward)")
                params["ward"] = ward
            
            if village:
                conditions.append("LOWER(village) = LOWER(:village)")
                params["village"] = village
            
            if status:
                conditions.append("status = :status")
                params["status"] = status
            
            if min_area is not None:
                conditions.append("area_hectares >= :min_area")
                params["min_area"] = min_area
            
            if max_area is not None:
                conditions.append("area_hectares <= :max_area")
                params["max_area"] = max_area
            
            if bbox:
                try:
                    minx, miny, maxx, maxy = map(float, bbox.split(','))
                    conditions.append("""
                        ST_Intersects(
                            geometry, 
                            ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326)
                        )
                    """)
                    params.update({
                        "minx": minx, "miny": miny, 
                        "maxx": maxx, "maxy": maxy
                    })
                except ValueError:
                    logger.warning(f"Invalid bbox format: {bbox}")
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            query = text(f"""
                SELECT 
                    id::text,
                    plot_code,
                    status,
                    area_hectares,
                    district,
                    ward,
                    village,
                    attributes,
                    created_at,
                    updated_at,
                    ST_AsGeoJSON(geometry)::json as geometry
                FROM land_plots
                {where_clause}
                ORDER BY plot_code
            """)
            
            result = db.execute(query, params)
            plots = result.fetchall()
            
            features = []
            for plot in plots:
                feature = {
                    "type": "Feature",
                    "properties": {
                        "id": plot.id,
                        "plot_code": plot.plot_code,
                        "status": plot.status,
                        "area_hectares": float(plot.area_hectares),
                        "district": plot.district,
                        "ward": plot.ward,
                        "village": plot.village,
                        "attributes": plot.attributes or {},
                        "created_at": plot.created_at.isoformat() + "Z",
                        "updated_at": plot.updated_at.isoformat() + "Z"
                    },
                    "geometry": plot.geometry
                }
                features.append(feature)
            
            return {
                "type": "FeatureCollection",
                "features": features
            }
            
        except Exception as e:
            logger.error(f"Error searching plots: {e}")
            raise
    
    def get_system_stats(self, db: Session) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            # Plot statistics
            plot_stats = db.execute(text("""
                SELECT 
                    COUNT(*) as total_plots,
                    COUNT(*) FILTER (WHERE status = 'available') as available_plots,
                    COUNT(*) FILTER (WHERE status = 'taken') as taken_plots,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_plots,
                    COUNT(DISTINCT district) as districts,
                    COUNT(DISTINCT ward) as wards,
                    COUNT(DISTINCT village) as villages,
                    SUM(area_hectares) as total_area_hectares
                FROM land_plots
            """)).fetchone()
            
            # Order statistics
            order_stats = db.execute(text("""
                SELECT 
                    COUNT(*) as total_orders,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_orders,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved_orders,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected_orders
                FROM plot_orders
            """)).fetchone()
            
            return {
                "total_plots": plot_stats.total_plots,
                "available_plots": plot_stats.available_plots,
                "taken_plots": plot_stats.taken_plots,
                "pending_plots": plot_stats.pending_plots,
                "total_orders": order_stats.total_orders,
                "pending_orders": order_stats.pending_orders,
                "approved_orders": order_stats.approved_orders,
                "rejected_orders": order_stats.rejected_orders,
                "districts": plot_stats.districts,
                "wards": plot_stats.wards,
                "villages": plot_stats.villages,
                "total_area_hectares": float(plot_stats.total_area_hectares or 0)
            }
            
        except Exception as e:
            logger.error(f"Error fetching system stats: {e}")
            raise