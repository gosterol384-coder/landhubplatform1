import { Plot, OrderData } from '../types/land';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Add debugging and better error handling
class PlotService {
  async getAllPlots(): Promise<Plot[]> {
    try {
      console.log('Fetching plots from:', `${API_BASE_URL}/api/plots`);
      const response = await fetch(`${API_BASE_URL}/api/plots`, {
        headers: {
          'Content-Type': 'application/json',
        },
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log('Received plot data:', { 
        type: data.type, 
        featureCount: data.features?.length || 0 
      });
      
      if (!data.features || !Array.isArray(data.features)) {
        throw new Error('Invalid GeoJSON response: missing features array');
      }
      
      return data.features.map((feature: any) => ({
        id: feature.properties.id,
        plot_code: feature.properties.plot_code,
        status: feature.properties.status,
        area_hectares: feature.properties.area_hectares,
        district: feature.properties.district,
        ward: feature.properties.ward,
        village: feature.properties.village,
        geometry: feature.geometry,
        attributes: feature.properties.attributes,
        created_at: feature.properties.created_at,
        updated_at: feature.properties.updated_at
      }));
    } catch (error) {
      console.error('Error fetching plots:', error);
      // Only return mock data if we're in development and API is not available
      if (import.meta.env.DEV && error instanceof TypeError) {
        console.warn('Using mock data for development');
        return this.getMockPlots();
      }
      throw error;
    }
  }

  async createOrder(plotId: string, orderData: OrderData): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/plots/${plotId}/order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(orderData),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error creating order:', error);
      throw error;
    }
  }

  private getMockPlots(): Plot[] {
    return [
      {
        id: '1',
        plot_code: 'DSM/KINONDONI/001',
        status: 'available',
        area_hectares: 0.5,
        district: 'Kinondoni',
        ward: 'Msasani',
        village: 'Msasani Peninsula',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [39.2734, -6.7732],
            [39.2744, -6.7732],
            [39.2744, -6.7742],
            [39.2734, -6.7742],
            [39.2734, -6.7732]
          ]]
        },
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z'
      },
      {
        id: '2',
        plot_code: 'DSM/KINONDONI/002',
        status: 'taken',
        area_hectares: 0.75,
        district: 'Kinondoni',
        ward: 'Msasani',
        village: 'Msasani Peninsula',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [39.2744, -6.7732],
            [39.2754, -6.7732],
            [39.2754, -6.7742],
            [39.2744, -6.7742],
            [39.2744, -6.7732]
          ]]
        },
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z'
      },
      {
        id: '3',
        plot_code: 'DSM/KINONDONI/003',
        status: 'available',
        area_hectares: 1.0,
        district: 'Kinondoni',
        ward: 'Msasani',
        village: 'Msasani Peninsula',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [39.2754, -6.7732],
            [39.2764, -6.7732],
            [39.2764, -6.7742],
            [39.2754, -6.7742],
            [39.2754, -6.7732]
          ]]
        },
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z'
      },
      {
        id: '4',
        plot_code: 'DSM/KINONDONI/004',
        status: 'pending',
        area_hectares: 0.6,
        district: 'Kinondoni',
        ward: 'Msasani',
        village: 'Msasani Peninsula',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [39.2734, -6.7742],
            [39.2744, -6.7742],
            [39.2744, -6.7752],
            [39.2734, -6.7752],
            [39.2734, -6.7742]
          ]]
        },
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z'
      }
    ];
  }
}

export const plotService = new PlotService();