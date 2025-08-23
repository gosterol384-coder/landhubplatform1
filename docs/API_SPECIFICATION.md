# Tanzania Land Plot System - API Specification

## Base URL
```
Production: https://your-backend.railway.app/api
Development: http://localhost:8000/api
```

## Authentication
This MVP version does not require authentication. All endpoints are publicly accessible with appropriate rate limiting.

## Endpoints

### 1. Get All Plots
Retrieve all land plots as GeoJSON FeatureCollection.

```http
GET /plots
```

#### Response (200 OK)
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "plot_code": "DSM/KINONDONI/001",
        "status": "available",
        "area_hectares": 0.5,
        "district": "Kinondoni",
        "ward": "Msasani",
        "village": "Msasani Peninsula",
        "attributes": {
          "land_use": "residential",
          "soil_type": "sandy"
        },
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z"
      },
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
          [
            [
              [39.2734, -6.7732],
              [39.2744, -6.7732],
              [39.2744, -6.7742],
              [39.2734, -6.7742],
              [39.2734, -6.7732]
            ]
          ]
        ]
      }
    }
  ]
}
```

### 2. Get Single Plot
Retrieve specific plot details.

```http
GET /plots/{plot_id}
```

#### Parameters
- `plot_id` (string, required): UUID of the plot

#### Response (200 OK)
```json
{
  "type": "Feature",
  "properties": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "plot_code": "DSM/KINONDONI/001",
    "status": "available",
    "area_hectares": 0.5,
    "district": "Kinondoni",
    "ward": "Msasani",
    "village": "Msasani Peninsula",
    "attributes": {},
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  },
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [...]
  }
}
```

#### Response (404 Not Found)
```json
{
  "detail": "Plot not found"
}
```

### 3. Create Plot Order
Submit an order for a specific plot.

```http
POST /plots/{plot_id}/order
```

#### Parameters
- `plot_id` (string, required): UUID of the plot

#### Request Body
```json
{
  "customer_name": "John Doe",
  "customer_phone": "+255123456789",
  "customer_email": "john@example.com",
  "customer_id_number": "19851201-12345-12345-12",
  "intended_use": "residential",
  "notes": "Looking for a plot near the main road"
}
```

#### Request Body Schema
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| customer_name | string | Yes | Full name of the customer |
| customer_phone | string | Yes | Phone number (with country code) |
| customer_email | string | No | Email address |
| customer_id_number | string | Yes | National ID number |
| intended_use | enum | Yes | One of: residential, commercial, agricultural, industrial, mixed |
| notes | string | No | Additional notes or requirements |

#### Response (201 Created)
```json
{
  "id": "456e7890-e89b-12d3-a456-426614174111",
  "plot_id": "123e4567-e89b-12d3-a456-426614174000",
  "customer_name": "John Doe",
  "customer_phone": "+255123456789",
  "customer_email": "john@example.com",
  "customer_id_number": "19851201-12345-12345-12",
  "intended_use": "residential",
  "notes": "Looking for a plot near the main road",
  "status": "pending",
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:00:00Z"
}
```

#### Response (400 Bad Request)
```json
{
  "detail": "Plot is not available for ordering"
}
```

#### Response (422 Unprocessable Entity)
```json
{
  "detail": [
    {
      "loc": ["body", "customer_phone"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 4. Get Plot Orders (Admin)
Retrieve all orders for administrative purposes.

```http
GET /orders
```

#### Query Parameters
- `status` (string, optional): Filter by order status (pending, approved, rejected)
- `plot_id` (string, optional): Filter by specific plot
- `limit` (integer, optional): Number of orders to return (default: 100)
- `offset` (integer, optional): Number of orders to skip (default: 0)

#### Response (200 OK)
```json
{
  "orders": [
    {
      "id": "456e7890-e89b-12d3-a456-426614174111",
      "plot_id": "123e4567-e89b-12d3-a456-426614174000",
      "plot_code": "DSM/KINONDONI/001",
      "customer_name": "John Doe",
      "customer_phone": "+255123456789",
      "customer_email": "john@example.com",
      "customer_id_number": "19851201-12345-12345-12",
      "intended_use": "residential",
      "notes": "Looking for a plot near the main road",
      "status": "pending",
      "created_at": "2025-01-01T12:00:00Z",
      "updated_at": "2025-01-01T12:00:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### 5. Update Order Status (Admin)
Update the status of an order.

```http
PUT /orders/{order_id}/status
```

#### Parameters
- `order_id` (string, required): UUID of the order

#### Request Body
```json
{
  "status": "approved",
  "notes": "Order approved by land officer"
}
```

#### Request Body Schema
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | enum | Yes | One of: pending, approved, rejected |
| notes | string | No | Admin notes about the status change |

#### Response (200 OK)
```json
{
  "id": "456e7890-e89b-12d3-a456-426614174111",
  "status": "approved",
  "updated_at": "2025-01-01T14:00:00Z",
  "admin_notes": "Order approved by land officer"
}
```

### 6. Search Plots
Search plots by various criteria.

```http
GET /plots/search
```

#### Query Parameters
- `district` (string, optional): Filter by district
- `ward` (string, optional): Filter by ward
- `village` (string, optional): Filter by village
- `status` (string, optional): Filter by availability status
- `min_area` (float, optional): Minimum area in hectares
- `max_area` (float, optional): Maximum area in hectares
- `bbox` (string, optional): Bounding box (minx,miny,maxx,maxy)

#### Example
```http
GET /plots/search?district=Kinondoni&status=available&min_area=0.5
```

#### Response (200 OK)
Same format as GET /plots

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid request parameters"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

## Rate Limiting
- 100 requests per minute per IP address
- 1000 requests per hour per IP address
- Rate limit headers included in responses

## CORS
- Allows all origins in development
- Restricted to specific domains in production
- Preflight requests handled automatically

## Data Formats

### Geometry Format
All geometries use GeoJSON format with WGS84 coordinate system (EPSG:4326).

### Date Format
All dates use ISO 8601 format with UTC timezone: `2025-01-01T12:00:00Z`

### Phone Format
Phone numbers should include country code: `+255123456789`

### Plot Code Format
Plot codes follow the pattern: `REGION/DISTRICT/SEQUENTIAL`
Example: `DSM/KINONDONI/001`