export interface Plot {
  id: string;
  plot_code: string;
  status: 'available' | 'taken' | 'pending';
  area_hectares: number;
  district: string;
  ward: string;
  village: string;
  geometry: GeoJSON.Geometry;
  attributes?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface OrderData {
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  customer_id_number: string;
  intended_use: 'residential' | 'commercial' | 'agricultural' | 'industrial' | 'mixed';
  notes?: string;
}

export interface Order {
  id: string;
  plot_id: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  customer_id_number: string;
  intended_use: string;
  notes?: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
}