import { Plot, OrderData } from '../types/land';

// Enhanced API configuration with fallback and validation
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_TIMEOUT = 30000; // 30 second timeout
const MAX_RETRIES = 3;

// Enhanced PlotService with comprehensive error handling and retry logic
class PlotService {
  private async fetchWithTimeout(url: string, options: RequestInit = {}): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);
    
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          ...options.headers,
        },
      });
      
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  private async retryRequest<T>(
    requestFn: () => Promise<T>,
    retries: number = MAX_RETRIES
  ): Promise<T> {
    try {
      return await requestFn();
    } catch (error) {
      if (retries > 0 && (error instanceof TypeError || (error as any)?.name === 'AbortError')) {
        console.log(`Request failed, retrying... (${MAX_RETRIES - retries + 1}/${MAX_RETRIES})`);
        await new Promise(resolve => setTimeout(resolve, 1000 * (MAX_RETRIES - retries + 1)));
        return this.retryRequest(requestFn, retries - 1);
      }
      throw error;
    }
  }
  async getAllPlots(): Promise<Plot[]> {
    return this.retryRequest(async () => {
      try {
        console.log('Fetching plots from:', `${API_BASE_URL}/api/plots`);
        console.log('Environment variables:', {
          VITE_API_URL: import.meta.env.VITE_API_URL,
          NODE_ENV: import.meta.env.NODE_ENV,
          DEV: import.meta.env.DEV,
          MODE: import.meta.env.MODE
        });
        
        const response = await this.fetchWithTimeout(`${API_BASE_URL}/api/plots`);
        
        if (!response.ok) {
          const errorText = await response.text().catch(() => 'Unknown error');
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const data = await response.json();
        console.log('Received plot data:', { 
          type: data.type, 
          featureCount: data.features?.length || 0,
          sampleFeature: data.features?.[0]?.properties
        });
        
        // Validate GeoJSON structure
        if (!data || typeof data !== 'object') {
          throw new Error('Invalid response: not a JSON object');
        }
        
        if (data.type !== 'FeatureCollection') {
          throw new Error(`Invalid GeoJSON: expected FeatureCollection, got ${data.type}`);
        }
        
        if (!data.features || !Array.isArray(data.features)) {
          throw new Error('Invalid GeoJSON: missing or invalid features array');
        }
        
        // Enhanced data validation and transformation with detailed logging
        const plots = data.features.map((feature: any, index: number) => {
          try {
            // Validate feature structure
            if (!feature || typeof feature !== 'object') {
              console.warn(`Feature ${index} is not a valid object`);
              return null;
            }
            
            if (feature.type !== 'Feature') {
              console.warn(`Feature ${index} has invalid type: ${feature.type}`);
              return null;
            }
            
            if (!feature.properties || typeof feature.properties !== 'object') {
              console.warn(`Feature ${index} missing or invalid properties`);
              return null;
            }
            
            if (!feature.geometry || typeof feature.geometry !== 'object') {
              console.warn(`Feature ${index} missing or invalid geometry`);
              return null;
            }
            
            // Validate required properties
            const props = feature.properties;
            if (!props.id || !props.plot_code) {
              console.warn(`Feature ${index} missing required properties (id, plot_code)`);
              return null;
            }
            
            // Validate geometry structure
            const geom = feature.geometry;
            if (!geom.type || !geom.coordinates) {
              console.warn(`Feature ${index} has invalid geometry structure`);
              return null;
            }
            
            if (!['Polygon', 'MultiPolygon'].includes(geom.type)) {
              console.warn(`Feature ${index} has unsupported geometry type: ${geom.type}`);
              return null;
            }
            
            // Validate coordinates array
            if (!Array.isArray(geom.coordinates) || geom.coordinates.length === 0) {
              console.warn(`Feature ${index} has invalid coordinates array`);
              return null;
            }
            
            return {
              id: String(props.id),
              plot_code: String(props.plot_code),
              status: props.status || 'available',
              area_hectares: Number(props.area_hectares) || 0,
              district: String(props.district || 'Unknown'),
              ward: String(props.ward || 'Unknown'),
              village: String(props.village || 'Unknown'),
              geometry: geom,
              attributes: props.attributes || {},
              created_at: props.created_at || new Date().toISOString(),
              updated_at: props.updated_at || new Date().toISOString()
            };
          } catch (error) {
            console.warn(`Error processing feature ${index}:`, error);
            return null;
          }
        }).filter(Boolean); // Remove null entries
        
        console.log(`Successfully processed ${plots.length} valid plots out of ${data.features.length} total features`);
        
        if (plots.length === 0) {
          console.warn('No valid plots found in API response');
          throw new Error('No valid plots found in the database');
        }
        
        return plots;
        
      } catch (error) {
        console.error('Error fetching plots:', error);
        
        // Enhanced error handling with specific error types
        if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
          console.warn('Network error: Backend API not available, using mock data for development');
          return this.getMockPlots();
        }
        
        if ((error as any)?.name === 'AbortError') {
          throw new Error('Request timed out. Please check your connection and try again.');
        }
        
        throw error;
      }
    });
  }

  async createOrder(plotId: string, orderData: OrderData): Promise<void> {
    return this.retryRequest(async () => {
      try {
        console.log(`Creating order for plot ${plotId}:`, orderData);
        
        const response = await this.fetchWithTimeout(`${API_BASE_URL}/api/plots/${plotId}/order`, {
          method: 'POST',
          body: JSON.stringify(orderData),
        });
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || `HTTP ${response.status}: ${response.statusText}`;
          throw new Error(errorMessage);
        }
        
        const result = await response.json();
        console.log('Order created successfully:', result);
        return result;
        
      } catch (error) {
        console.error('Error creating order:', error);
        
        if ((error as any)?.name === 'AbortError') {
          throw new Error('Order submission timed out. Please try again.');
        }
        
        throw error;
      }
    });
  }

  // Enhanced mock data with more realistic Tanzania plot data
  private getMockPlots(): Plot[] {
    console.log('Using mock plot data for development');
    return [
      {
        id: '1',
        plot_code: 'DSM/KINONDONI/001',
        status: 'available',
        area_hectares: 0.5,
        district: 'Kinondoni',
        ward: 'Msasani',
        village: 'Msasani Peninsula',
        attributes: {
          land_use: 'residential',
          soil_type: 'sandy',
          elevation: 45
        },
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
        attributes: {
          land_use: 'commercial',
          soil_type: 'clay'
        },
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
        attributes: {
          land_use: 'mixed',
          soil_type: 'loam'
        },
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
        attributes: {
          land_use: 'residential',
          soil_type: 'sandy'
        },
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
      },
      {
        id: '5',
        plot_code: 'DSM/KINONDONI/005',
        status: 'available',
        area_hectares: 2.5,
        district: 'Kinondoni',
        ward: 'Msasani',
        village: 'Msasani Peninsula',
        attributes: {
          land_use: 'agricultural',
          soil_type: 'fertile',
          water_access: true
        },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [39.2764, -6.7732],
            [39.2784, -6.7732],
            [39.2784, -6.7762],
            [39.2764, -6.7762],
            [39.2764, -6.7732]
          ]]
        },
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z'
      }
    ];
  }

  // Health check method for system diagnostics
  async checkHealth(): Promise<boolean> {
    try {
      const response = await this.fetchWithTimeout(`${API_BASE_URL}/health`);
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }

  // Get system statistics
  async getStats(): Promise<any> {
    try {
      const response = await this.fetchWithTimeout(`${API_BASE_URL}/api/stats`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching stats:', error);
      throw error;
    ];
  }
}

export const plotService = new PlotService();