from pydantic import BaseModel, EmailStr, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

class PlotStatus(str, Enum):
    available = "available"
    taken = "taken"
    pending = "pending"

class IntendedUse(str, Enum):
    residential = "residential"
    commercial = "commercial"
    agricultural = "agricultural"
    industrial = "industrial"
    mixed = "mixed"

class OrderStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class PlotOrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[EmailStr] = None
    customer_id_number: str
    intended_use: IntendedUse
    notes: Optional[str] = None
    
    @validator('customer_name')
    def validate_customer_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Customer name must be at least 2 characters long')
        return v.strip()
    
    @validator('customer_phone')
    def validate_customer_phone(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError('Customer phone must be at least 10 characters long')
        # Basic Tanzania phone number validation
        phone = v.strip().replace(' ', '').replace('-', '')
        if not phone.startswith('+255') and not phone.startswith('255') and not phone.startswith('0'):
            raise ValueError('Phone number must be a valid Tanzania number')
        return phone
    
    @validator('customer_id_number')
    def validate_customer_id_number(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError('Customer ID number must be at least 5 characters long')
        return v.strip()

class PlotOrderResponse(BaseModel):
    id: str
    plot_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str]
    customer_id_number: str
    intended_use: str
    notes: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    notes: Optional[str] = None

class PlotProperties(BaseModel):
    id: str
    plot_code: str
    status: str
    area_hectares: float
    district: str
    ward: str
    village: str
    attributes: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class PlotFeature(BaseModel):
    type: str = "Feature"
    properties: PlotProperties
    geometry: Dict[str, Any]

class PlotFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[PlotFeature]

class OrderWithPlot(BaseModel):
    id: str
    plot_id: str
    plot_code: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str]
    customer_id_number: str
    intended_use: str
    notes: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SystemStats(BaseModel):
    total_plots: int
    available_plots: int
    taken_plots: int
    pending_plots: int
    total_orders: int
    pending_orders: int
    approved_orders: int
    rejected_orders: int
    districts: int
    wards: int
    villages: int
    total_area_hectares: float

class ShapefileImport(BaseModel):
    dataset_name: str
    prj: Optional[str] = None
    cpg: Optional[str] = None
    dbf_schema: Dict[str, Any]
    file_hashes: Optional[Dict[str, str]] = None
    feature_count: int
    imported_at: datetime
    bbox: Optional[Dict[str, Any]] = None  # GeoJSON Polygon

class ShapefileImportList(BaseModel):
    imports: List[ShapefileImport]