from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import logging
from contextlib import asynccontextmanager

from database import get_db, engine
from models import LandPlot, PlotOrder
from schemas import PlotOrderCreate, PlotOrderResponse, OrderStatusUpdate, ShapefileImport, ShapefileImportList
from services.plot_service import PlotService
from services.order_service import OrderService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Tanzania Land Plot API...")
    try:
        # Test database connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            logger.info(f"Database connected: {result.fetchone()[0]}")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Tanzania Land Plot API...")

app = FastAPI(
    title="Tanzania Land Plot API",
    description="API for Tanzania Land Plot Ordering System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
plot_service = PlotService()
order_service = OrderService()

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Tanzania Land Plot API",
        "version": "1.0.0",
        "status": "healthy"
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Detailed health check with database connectivity"""
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": "2025-01-01T00:00:00Z"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e)
            }
        )

@app.get("/api/plots")
async def get_all_plots(db: Session = Depends(get_db)):
    """Get all land plots as GeoJSON FeatureCollection"""
    try:
        logger.info("GET /api/plots - Fetching all plots")
        plots_geojson = plot_service.get_all_plots_geojson(db)
        feature_count = len(plots_geojson.get('features', []))
        logger.info(f"Returning {feature_count} plot features")
        return plots_geojson
    except Exception as e:
        logger.error(f"Error fetching plots: {e}")

@app.get("/api/plots/{plot_id}")
async def get_plot(plot_id: str, db: Session = Depends(get_db)):
    """Get specific plot details"""
    try:
        plot_geojson = plot_service.get_plot_geojson(db, plot_id)
        if not plot_geojson:
            raise HTTPException(status_code=404, detail="Plot not found")
        return plot_geojson
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching plot {plot_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch plot")

@app.post("/api/plots/{plot_id}/order", response_model=PlotOrderResponse)
async def create_plot_order(
    plot_id: str, 
    order_data: PlotOrderCreate, 
    db: Session = Depends(get_db)
):
    """Create an order for a specific plot"""
    try:
        # Check if plot exists and is available
        plot = plot_service.get_plot_by_id(db, plot_id)
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        
        if plot.status != 'available':
            raise HTTPException(
                status_code=400, 
                detail=f"Plot is not available for ordering. Current status: {plot.status}"
            )
        
        # Create the order
        order = order_service.create_order(db, plot_id, order_data)
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order for plot {plot_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")

@app.get("/api/orders")
async def get_orders(
    status: Optional[str] = Query(None, description="Filter by order status"),
    plot_id: Optional[str] = Query(None, description="Filter by plot ID"),
    limit: int = Query(100, ge=1, le=1000, description="Number of orders to return"),
    offset: int = Query(0, ge=0, description="Number of orders to skip"),
    db: Session = Depends(get_db)
):
    """Get all orders with optional filtering"""
    try:
        orders, total = order_service.get_orders(
            db, status=status, plot_id=plot_id, limit=limit, offset=offset
        )
        
        return {
            "orders": orders,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

@app.put("/api/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    status_update: OrderStatusUpdate,
    db: Session = Depends(get_db)
):
    """Update order status (admin function)"""
    try:
        updated_order = order_service.update_order_status(
            db, order_id, status_update.status, status_update.notes
        )
        
        if not updated_order:
            raise HTTPException(status_code=404, detail="Order not found")
            
        return {
            "id": updated_order.id,
            "status": updated_order.status,
            "updated_at": updated_order.updated_at.isoformat() + "Z",
            "admin_notes": status_update.notes
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating order {order_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update order status")

@app.get("/api/plots/search")
async def search_plots(
    district: Optional[str] = Query(None, description="Filter by district"),
    ward: Optional[str] = Query(None, description="Filter by ward"),
    village: Optional[str] = Query(None, description="Filter by village"),
    status: Optional[str] = Query(None, description="Filter by availability status"),
    min_area: Optional[float] = Query(None, ge=0, description="Minimum area in hectares"),
    max_area: Optional[float] = Query(None, ge=0, description="Maximum area in hectares"),
    bbox: Optional[str] = Query(None, description="Bounding box (minx,miny,maxx,maxy)"),
    db: Session = Depends(get_db)
):
    """Search plots by various criteria"""
    try:
        plots_geojson = plot_service.search_plots(
            db,
            district=district,
            ward=ward,
            village=village,
            status=status,
            min_area=min_area,
            max_area=max_area,
            bbox=bbox
        )
        return plots_geojson
    except Exception as e:
        logger.error(f"Error searching plots: {e}")
        raise HTTPException(status_code=500, detail="Failed to search plots")

@app.get("/api/stats")
async def get_system_stats(db: Session = Depends(get_db)):
    """Get system statistics"""
    try:
        stats = plot_service.get_system_stats(db)
        return stats
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")

@app.get("/api/imports", response_model=ShapefileImportList)
async def list_shapefile_imports(db: Session = Depends(get_db)):
    """List shapefile import metadata."""
    try:
        rows = db.execute(text("""
            SELECT dataset_name, prj, cpg, dbf_schema, file_hashes, feature_count, imported_at,
                   CASE WHEN bbox IS NOT NULL THEN ST_AsGeoJSON(bbox)::json ELSE NULL END AS bbox
            FROM shapefile_imports ORDER BY imported_at DESC
        """)).fetchall()
        data = []
        for r in rows:
            data.append({
                "dataset_name": r.dataset_name,
                "prj": r.prj,
                "cpg": r.cpg,
                "dbf_schema": r.dbf_schema or {},
                "file_hashes": r.file_hashes or {},
                "feature_count": r.feature_count,
                "imported_at": r.imported_at,
                "bbox": r.bbox
            })
        return {"imports": data}
    except Exception as e:
        logger.error(f"Error listing shapefile imports: {e}")
        raise HTTPException(status_code=500, detail="Failed to list shapefile imports")

@app.get("/api/imports/{dataset_name}", response_model=ShapefileImport)
async def get_shapefile_import(dataset_name: str, db: Session = Depends(get_db)):
    """Get metadata for a specific shapefile import."""
    try:
        row = db.execute(text("""
            SELECT dataset_name, prj, cpg, dbf_schema, file_hashes, feature_count, imported_at,
                   CASE WHEN bbox IS NOT NULL THEN ST_AsGeoJSON(bbox)::json ELSE NULL END AS bbox
            FROM shapefile_imports WHERE dataset_name = :d
        """), {"d": dataset_name}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return {
            "dataset_name": row.dataset_name,
            "prj": row.prj,
            "cpg": row.cpg,
            "dbf_schema": row.dbf_schema or {},
            "file_hashes": row.file_hashes or {},
            "feature_count": row.feature_count,
            "imported_at": row.imported_at,
            "bbox": row.bbox
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching shapefile import {dataset_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch shapefile import metadata")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)