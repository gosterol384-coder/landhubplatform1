from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
import uuid

Base = declarative_base()

class LandPlot(Base):
    __tablename__ = "land_plots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plot_code = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(
        String(20), 
        nullable=False, 
        default='available',
        index=True
    )
    area_hectares = Column(Numeric(10, 4), nullable=False)
    district = Column(String(100), nullable=False, index=True)
    ward = Column(String(100), nullable=False)
    village = Column(String(100), nullable=False)
    dataset_name = Column(String(100), nullable=True, index=True)
    dataset_name = Column(String(100), nullable=True, index=True)
    geometry = Column(Geometry('MULTIPOLYGON', srid=4326), nullable=False)
    attributes = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    orders = relationship("PlotOrder", back_populates="plot")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'taken', 'pending')",
            name='check_plot_status'
        ),
    )
    
    def __repr__(self):
        return f"<LandPlot(plot_code='{self.plot_code}', status='{self.status}')>"

class ShapefileImport(Base):
    __tablename__ = "shapefile_imports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_name = Column(String(100), unique=True, nullable=False, index=True)
    prj = Column(Text, nullable=True)  # Projection information
    cpg = Column(String(50), nullable=True)  # Code page/encoding
    dbf_schema = Column(JSONB, default={})  # DBF field schema
    file_hashes = Column(JSONB, default={})  # SHA-256 hashes of all components
    feature_count = Column(Numeric, nullable=False, default=0)
    bbox = Column(Geometry('POLYGON', srid=4326), nullable=True)  # Bounding box
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
class PlotOrder(Base):
    __tablename__ = "plot_orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plot_id = Column(UUID(as_uuid=True), ForeignKey('land_plots.id'), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    customer_email = Column(String(200), nullable=True)
    customer_id_number = Column(String(50), nullable=False, index=True)
    intended_use = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(
        String(20), 
        nullable=False, 
        default='pending',
        index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    plot = relationship("LandPlot", back_populates="orders")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "intended_use IN ('residential', 'commercial', 'agricultural', 'industrial', 'mixed')",
            name='check_intended_use'
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name='check_order_status'
        ),
    )
    
    def __repr__(self):
        return f"<PlotOrder(customer_name='{self.customer_name}', status='{self.status}')>"