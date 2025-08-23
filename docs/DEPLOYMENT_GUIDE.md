# Tanzania Land Plot System - Deployment Guide

## Overview
This guide covers deploying the Tanzania Land Plot System across three platforms:
- **Frontend**: Netlify (React application)
- **Database**: Supabase (PostgreSQL + PostGIS)
- **Backend**: Railway (FastAPI Python application)

## 1. Database Setup (Supabase)

### Step 1: Create Supabase Project
1. Go to [supabase.com](https://supabase.com) and create a new project
2. Note down your project URL and API keys
3. Enable PostGIS extension in SQL Editor:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```

### Step 2: Run Database Schema
1. In Supabase SQL Editor, run the complete schema from `database/schema.sql`
2. This creates all tables, indexes, RLS policies, and sample data
3. Verify PostGIS extension is working:
   ```sql
   SELECT PostGIS_Version();
   ```

### Step 3: Configure Row Level Security
- The schema automatically sets up RLS policies
- Plots are publicly readable
- Orders can be created by anyone
- This is suitable for an MVP without authentication

## 2. Backend Setup (FastAPI on Railway/Render)

### Step 1: Prepare Backend Files
The backend is located in the `backend/` directory with the following structure:
```
backend/
├── main.py              # FastAPI app entry point
├── database.py          # Database connection
├── models.py            # SQLAlchemy models
├── schemas.py           # Pydantic schemas
├── services/
│   ├── plot_service.py  # Plot business logic
│   └── order_service.py # Order business logic
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
├── railway.json        # Railway deployment config
└── .env.example        # Environment variables template
```

### Required Python Dependencies
See `backend/requirements.txt` for the complete list of dependencies.

### Environment Variables
Create a `.env` file in the backend directory:
```env
DATABASE_URL=postgresql://postgres:password@db.supabaseproject.co:5432/postgres
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_KEY=your_supabase_anon_key
ENVIRONMENT=production
CORS_ORIGINS=https://your-frontend.netlify.app
```

### Step 2: Deploy to Railway
1. Create account at [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Create a new project and select the repository
4. Railway will automatically detect the Python application
5. Add environment variables in Railway dashboard:
   - `DATABASE_URL`: Your Supabase PostgreSQL connection string
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_KEY`: Your Supabase anon key
   - `ENVIRONMENT`: `production`
   - `CORS_ORIGINS`: Your Netlify frontend URL

### Step 3: Configure Railway Settings
Railway will use the `railway.json` configuration file which specifies:
- Docker build using the provided Dockerfile
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check endpoint: `/health`
- Restart policy for reliability

### Step 4: Test Backend Deployment
Once deployed, test the API endpoints:
```bash
# Health check
curl https://your-backend.railway.app/health

# Get plots
curl https://your-backend.railway.app/api/plots

# Get system stats
curl https://your-backend.railway.app/api/stats
```

## 3. Frontend Setup (Netlify)

### Environment Variables (.env)
Create environment variables in Netlify dashboard:
```env
VITE_API_URL=https://your-backend.railway.app
VITE_SUPABASE_URL=https://yourproject.supabase.co
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
VITE_ENVIRONMENT=production
```

### Build Configuration
The `netlify.toml` file is already configured with:
- Build command: `npm run build`
- Publish directory: `dist`
- API redirects to backend
- SPA fallback routing
- Security headers

### Deploy to Netlify
1. Connect GitHub repository to Netlify
2. Set build command: `npm run build`
3. Set publish directory: `dist`
4. Add environment variables in Netlify dashboard
5. Enable automatic deployments from main branch
6. Update the API redirect URL in `netlify.toml` to point to your Railway backend

## 4. Complete Integration Steps

### Step 1: Update Configuration Files
1. Update `netlify.toml` with your Railway backend URL
2. Update frontend environment variables with actual URLs
3. Update backend CORS origins with your Netlify URL

### Step 2: Test Full Integration
1. Deploy backend to Railway
2. Deploy frontend to Netlify
3. Test the complete workflow:
   - Load map with plots
   - Click on available plot
   - Submit order form
   - Verify plot status changes

### Step 3: Monitor Deployments
- Railway: Monitor logs and metrics in Railway dashboard
- Netlify: Check build logs and function logs
- Supabase: Monitor database performance and queries

## 5. Shapefile Import Pipeline

### Tools Required
- GDAL/OGR tools (ogr2ogr)
- PostGIS database access

### Import Process
```bash
# 1. Inspect shapefile
ogrinfo -al your_plots.shp

# 2. Transform and import to PostGIS
ogr2ogr -f "PostgreSQL" \
  "PG:host=db.supabaseproject.co port=5432 dbname=postgres user=postgres password=yourpassword" \
  your_plots.shp \
  -nln land_plots_import \
  -t_srs EPSG:4326 \
  -overwrite \
  -progress

# 3. Process imported data with SQL
```

### SQL Processing Script
```sql
-- Insert processed data from import table
INSERT INTO land_plots (
  plot_code, status, area_hectares, district, ward, village, geometry, attributes
)
SELECT 
  COALESCE(plot_code, 'PLOT_' || row_number() OVER()) as plot_code,
  'available' as status,
  ST_Area(ST_Transform(wkb_geometry, 32737)) / 10000.0 as area_hectares, -- Convert to hectares
  COALESCE(district, 'Unknown') as district,
  COALESCE(ward, 'Unknown') as ward,
  COALESCE(village, 'Unknown') as village,
  ST_Multi(ST_Transform(wkb_geometry, 4326)) as geometry,
  to_jsonb(row_to_json(import_table)) - 'wkb_geometry' as attributes
FROM land_plots_import import_table;

-- Drop import table
DROP TABLE land_plots_import;
```

## 5. Production Considerations

### Performance
- Spatial indexes on geometry columns
- Connection pooling for database
- CDN for static assets (Netlify handles this)
- Caching for plot data

### Security
- Rate limiting on API endpoints
- Input validation and sanitization
- CORS configuration for production domains
- Environment variable security

### Monitoring
- Database performance monitoring in Supabase
- Application logs in Railway/Render
- Error tracking (Sentry integration)
- Uptime monitoring

### Scaling
- Database: Supabase handles scaling automatically
- Backend: Railway/Render provide easy scaling options
- Frontend: Netlify CDN provides global distribution

## 6. Tanzania-Specific Configurations

### Coordinate Systems
- Input: Various (UTM Zone 36S/37S, Arc 1960, etc.)
- Output: WGS84 (EPSG:4326) for web mapping
- Area calculations: Use appropriate UTM zone (32736/32737)

### Data Standards
- Plot codes: REGION/DISTRICT/SEQUENTIAL
- Administrative levels: Region > District > Ward > Village
- Area units: Hectares (conversion from square meters)

### Map Configuration
- Center: Tanzania centroid (-6.369028, 34.888822)
- Zoom levels: Country (6) to Plot detail (18)
- Base layers: OpenStreetMap or Tanzania-specific tiles

This system is production-ready for MVP deployment and can handle real Tanzania shapefile data with proper spatial transformations and indexing.