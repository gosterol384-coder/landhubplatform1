from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/tanzania_land_plots"
)

# Handle Railway/Render PostgreSQL URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,  # Set to True for SQL debugging
    connect_args={
        "options": "-c timezone=UTC",
        "application_name": "tanzania_land_system"
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

def create_tables():
    """Create all database tables"""
    try:
        # Import models to ensure they're registered
        from models import LandPlot, PlotOrder, ShapefileImport
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
        
        # Ensure PostGIS extension
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
            conn.commit()
            logger.info("PostGIS extension ensured")
            
        return True
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return False
def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"Database connection successful: {version}")
            
            # Test PostGIS
            result = conn.execute(text("SELECT PostGIS_Version()"))
            postgis_version = result.fetchone()[0]
            logger.info(f"PostGIS version: {postgis_version}")
            
            # Test spatial functions
            result = conn.execute(text("""
                SELECT ST_AsText(ST_GeomFromText('POINT(0 0)', 4326))
            """))
            point_test = result.fetchone()[0]
            logger.info(f"Spatial function test: {point_test}")
            
            return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False

if __name__ == "__main__":
    if test_connection():
        create_tables()