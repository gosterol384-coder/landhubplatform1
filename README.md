# Tanzania Land Plot Ordering System

A comprehensive web application for managing Tanzania land plot data with interactive mapping, shapefile import capabilities, and real-time order processing.

## 🌟 Features

- **Interactive Map**: Leaflet-based map displaying land plots with color-coded availability status
- **Shapefile Import**: Complete pipeline for importing Tanzania land plot shapefiles with CRS transformation
- **Real-time Orders**: Click-to-order workflow with instant plot status updates
- **Spatial Database**: PostgreSQL + PostGIS for efficient spatial data handling
- **RESTful API**: FastAPI backend with GeoJSON endpoints
- **Responsive Design**: Works on desktop and mobile devices for field operations

## 🏗️ Architecture

- **Frontend**: React + TypeScript + Tailwind CSS + Leaflet
- **Backend**: FastAPI + SQLAlchemy + GeoAlchemy2
- **Database**: PostgreSQL + PostGIS (Supabase)
- **Deployment**: Netlify (frontend) + Railway (backend) + Supabase (database)

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- PostgreSQL with PostGIS extension

### Frontend Setup

```bash
# Install dependencies
npm install

# Create environment file
cp .env.example .env

# Update .env with your API URL
VITE_API_URL=http://localhost:8000

# Start development server
npm run dev
```

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Update .env with your database URL
DATABASE_URL=postgresql://user:password@localhost:5432/tanzania_plots

# Start the API server
uvicorn main:app --reload
```

### Database Setup

1. Create PostgreSQL database with PostGIS extension
2. Run the migration script:
   ```sql
   -- Run the contents of supabase/migrations/20250822175130_mellow_cottage.sql
   ```

## 📊 API Endpoints

### Core Endpoints

- `GET /api/plots` - Get all plots as GeoJSON FeatureCollection
- `GET /api/plots/{plot_id}` - Get specific plot details
- `POST /api/plots/{plot_id}/order` - Create order for a plot
- `GET /api/orders` - List all orders (admin)
- `PUT /api/orders/{order_id}/status` - Update order status
- `GET /api/plots/search` - Search plots with filters
- `GET /api/stats` - Get system statistics

### Example Usage

```bash
# Get all plots
curl https://your-api.railway.app/api/plots

# Create an order
curl -X POST https://your-api.railway.app/api/plots/{plot_id}/order \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "John Doe",
    "customer_phone": "+255123456789",
    "customer_id_number": "12345678",
    "intended_use": "residential"
  }'
```

## 🗺️ Shapefile Import

The system supports importing Tanzania land plot shapefiles with automatic coordinate transformation:

```bash
# Import shapefile using ogr2ogr
ogr2ogr -f "PostgreSQL" \
  "PG:host=localhost port=5432 dbname=tanzania_plots user=postgres" \
  your_plots.shp \
  -nln land_plots_import \
  -t_srs EPSG:4326 \
  -s_srs EPSG:21096 \
  -overwrite
```

See `docs/SHAPEFILE_IMPORT.md` for detailed import instructions.

## 🚀 Deployment

### Production Deployment

1. **Database (Supabase)**:
   - Create Supabase project
   - Enable PostGIS extension
   - Run database migrations

2. **Backend (Railway)**:
   - Connect GitHub repository
   - Set environment variables
   - Deploy automatically

3. **Frontend (Netlify)**:
   - Connect GitHub repository
   - Set build command: `npm run build`
   - Set environment variables

See `docs/DEPLOYMENT_GUIDE.md` for detailed deployment instructions.

## 🛠️ Development

### Project Structure

```
├── src/                    # Frontend React application
│   ├── components/         # React components
│   ├── services/          # API services
│   ├── types/             # TypeScript types
│   └── styles/            # CSS styles
├── backend/               # FastAPI backend
│   ├── services/          # Business logic
│   ├── models.py          # Database models
│   ├── schemas.py         # Pydantic schemas
│   └── main.py           # FastAPI app
├── supabase/migrations/   # Database migrations
└── docs/                 # Documentation
```

### Key Technologies

- **Frontend**: React 18, TypeScript, Tailwind CSS, Leaflet
- **Backend**: FastAPI, SQLAlchemy, GeoAlchemy2, Pydantic
- **Database**: PostgreSQL, PostGIS
- **Spatial**: GeoJSON, WGS84 (EPSG:4326)

### Shapefile Seeding (MVS)

Load sample `test_mbuyuni` shapefile into PostGIS:
```bash
cd backend
python seed_import.py --shapefile data/test_mbuyuni/test_mbuyuni.shp --district Mbuyuni --ward Mbuyuni --village Mbuyuni
```
Prerequisites:
* PostGIS-enabled DB (Supabase / local) set in `backend/.env` as `DATABASE_URL`.
* `ogr2ogr` (GDAL). If absent install Python fallback deps: `pip install fiona shapely pyproj`.

Process summary: ensures schema, imports to temp table, transforms CRS -> 4326, enforces MultiPolygon, computes `area_hectares`, stores original fields in `attributes`, skips existing `plot_code`s.
See `docs/ARCHITECTURE_MVS.md` for full details.

## 📋 Tanzania-Specific Features

- **Coordinate Systems**: Support for Arc 1960 UTM and WGS84 transformations
- **Administrative Levels**: Region > District > Ward > Village hierarchy
- **Plot Codes**: Format: `REGION/DISTRICT/SEQUENTIAL` (e.g., `DSM/KINONDONI/001`)
- **Area Calculations**: Hectare-based measurements
- **Phone Validation**: Tanzania phone number formats (+255)

## 🔧 Configuration

### Environment Variables

**Frontend (.env)**:
```env
VITE_API_URL=https://your-backend.railway.app
VITE_SUPABASE_URL=https://yourproject.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key
```

**Backend (.env)**:
```env
DATABASE_URL=postgresql://user:pass@host:5432/db
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_KEY=your_anon_key
CORS_ORIGINS=https://your-frontend.netlify.app
```

## 📚 Documentation

- [API Specification](docs/API_SPECIFICATION.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Shapefile Import](docs/SHAPEFILE_IMPORT.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Check the documentation in the `docs/` directory
- Review the API specification
- Check deployment guides for platform-specific issues

## 🎯 Roadmap

- [ ] User authentication and authorization
- [ ] Admin dashboard for order management
- [ ] Bulk shapefile import interface
- [ ] Payment integration
- [ ] Mobile app development
- [ ] Advanced spatial analysis tools