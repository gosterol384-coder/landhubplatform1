# Tanzania Land Plot Ordering MVS Architecture

## 1. Overview
Minimal viable system to ingest Tanzanian land plot shapefiles, expose them via a FastAPI + PostGIS backend, and allow end‑users to submit plot orders through a React + Leaflet single page map interface.

## 2. Core Components
| Component | Technology | Responsibility |
|-----------|------------|----------------|
| Spatial DB | PostgreSQL + PostGIS | Store land parcels (MultiPolygon), attributes, orders, spatial indexes |
| API | FastAPI | CRUD/query for plots and orders, GeoJSON responses, stats |
| ORM / Spatial Layer | SQLAlchemy + GeoAlchemy2 | Data access, geometry types |
| Import Pipeline | ogr2ogr (preferred) / Fiona+Shapely fallback | Shapefile -> PostGIS ingest + normalization |
| Frontend | React (Vite) + Leaflet + Tailwind | Interactive map, plot selection, order workflow |

## 3. Database Schema (DDL)
See `backend/schema.sql` for executable DDL (extensions, tables, constraints, indexes, triggers).
Highlights:
* Geometry column: `geometry(MultiPolygon,4326)` ensuring WGS84.
* Status constraints for plots and orders.
* JSONB `attributes` retains original shapefile fields.
* Spatial GIST index for fast bounding box / intersection queries.
* Trigger keeps `updated_at` current.

### Area Storage Strategy
`area_hectares` computed at import using projected area (Web Mercator transformation) then converted to hectares. For more precise cadastral area you may project to a local UTM zone or use `ST_Area(geography(geometry))/10000`.

## 4. Shapefile Import Pipeline
1. Place shapefile component files (`.shp/.shx/.dbf/.prj/.cpg`) in `backend/data/<dataset>/`.
2. Run seed script:
   ```bash
   cd backend
   python seed_import.py --shapefile data/test_mbuyuni/test_mbuyuni.shp --district Mbuyuni --ward Mbuyuni --village Mbuyuni
   ```
3. Script actions:
   * Ensures schema (runs `schema.sql`).
   * Imports shapefile to temporary table via `ogr2ogr` (forces MultiPolygon, transforms CRS to EPSG:4326). Fallback uses Fiona/Shapely if GDAL not installed.
   * Determines a plot code attribute if present; else generates sequential `MBY-0001` style codes.
   * Computes `area_hectares` and inserts new rows avoiding duplicates on `plot_code`.
   * Drops temporary import table.

### CRS Handling
* Always transformed to `EPSG:4326` using `ogr2ogr -t_srs EPSG:4326` or Fiona+pyproj transformer.
* MultiPolygon enforced (single Polygon wrapped) for uniform storage.

## 5. API Specification (Key Endpoints)

### GET /api/plots
Returns: `GeoJSON FeatureCollection`
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "uuid",
        "plot_code": "MBY-0001",
        "status": "available",
        "area_hectares": 0.42,
        "district": "Mbuyuni",
        "ward": "Mbuyuni",
        "village": "Mbuyuni",
        "attributes": { "SOURCE_FIELD": "value" },
        "created_at": "2025-08-23T10:00:00Z",
        "updated_at": "2025-08-23T10:00:00Z"
      },
      "geometry": {"type": "MultiPolygon", "coordinates": [[[ [... ] ]]]}
    }
  ]
}
```

### GET /api/plots/{plot_id}
Returns single GeoJSON Feature or 404.

### GET /api/plots/search?district=&status=&min_area=&max_area=&bbox=
Filterable search returning GeoJSON FeatureCollection. `bbox` format: `minx,miny,maxx,maxy` in WGS84.

### POST /api/plots/{plot_id}/order
Request:
```json
{
  "customer_name": "Jane Doe",
  "customer_phone": "+255712345678",
  "customer_email": "jane@example.com",
  "customer_id_number": "ID12345",
  "intended_use": "residential",
  "notes": "Urgent"
}
```
Response (201 implicit via FastAPI model):
```json
{
  "id": "order-uuid",
  "plot_id": "plot-uuid",
  "customer_name": "Jane Doe",
  "customer_phone": "+255712345678",
  "customer_email": "jane@example.com",
  "customer_id_number": "ID12345",
  "intended_use": "residential",
  "notes": "Urgent",
  "status": "pending",
  "created_at": "2025-08-23T10:05:00Z",
  "updated_at": "2025-08-23T10:05:00Z"
}
```
Errors: 404 (plot not found), 400 (plot not available), 422 (validation), 500.

### GET /api/orders
Paginated list with optional `status` or `plot_id` filters.

### PUT /api/orders/{order_id}/status
Body: `{ "status": "approved", "notes": "All docs verified" }`.
Updates plot status to `taken` if approved or resets to `available` on rejection when no other pending orders.

### GET /api/stats
Returns aggregate counters & total area.

## 6. Frontend Map (React + Leaflet)
Implemented in `src/components/MapView.tsx`:
* Fetches `/api/plots` once on mount and renders polygons.
* Styling colors: available=green, taken=red, pending=yellow.
* Popup includes button to initiate order; opens `PlotOrderModal` which posts order to backend.
* On success: local state updated + map layer re-rendered, giving real-time feel (polling/websocket optional later).

## 7. Data Flow
1. Shapefile ingestion: `seed_import.py` -> temporary table -> normalized insert into `land_plots`.
2. User loads app: React fetches `/api/plots` -> GeoJSON -> Leaflet layer.
3. User clicks polygon: popup -> order modal -> POST order.
4. Backend transaction: create order + set plot status to `pending`.
5. Frontend updates color to yellow immediately (pending).
6. (Future admin) Approves order -> `PUT /api/orders/{id}/status` sets plot `taken` or reverts.
7. Stats endpoint aggregates counts for dashboards (future extension).

## 8. Error Handling & Integrity
* Database constraints enforce valid statuses & geometry presence.
* Transactional order creation/update ensures plot status consistency.
* Duplicate plot codes ignored on re-import to allow incremental updates.
* Logging at each layer for traceability.

## 9. Performance Considerations
* GIST spatial index enables fast map bounding box queries (`/api/plots/search?bbox=`).
* Only required fields returned; geometry served as GeoJSON directly from PostGIS (`ST_AsGeoJSON`).
* Future: tile generation / vector tiles for large datasets (beyond MVS scope).

## 10. Future Enhancements
* WebSocket / Server-Sent Events for real-time status broadcasting.
* Authentication & role-based admin approval UI.
* Bulk import + delta updates (tracking source file version metadata table).
* Vector tile service for scalable map rendering (tegola / postgis-vector-tile functions).
* Advanced spatial filters (within district boundary polygons, proximity searches).

## 11. Supabase Considerations
* Supabase Postgres compatible; ensure PostGIS extension enabled in the project.
* Use SQL editor to run `schema.sql` then run `seed_import.py` locally pointing to Supabase connection string (already set in `.env`).

---
This document captures the minimal yet production-aware design required for the initial release.
