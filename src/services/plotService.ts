import { Plot, OrderData, Order } from '../types/land';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class PlotService {
  private async fetchWithErrorHandling(url: string, options?: RequestInit): Promise<Response> {
    try {
      console.log(`Making API request to: ${url}`);
      
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`API Error ${response.status}:`, errorText);
        
        let errorMessage = `HTTP ${response.status}`;
        try {
          const errorJson = JSON.parse(errorText);
          errorMessage = errorJson.detail || errorJson.message || errorMessage;
        } catch {
          errorMessage = errorText || errorMessage;
        }
        
        throw new Error(errorMessage);
      }

      return response;
    } catch (error) {
      console.error('Network error:', error);
      
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('Unable to connect to the server. Please check your internet connection and try again.');
      }
      
      throw error;
    }
  }

  async getAllPlots(): Promise<Plot[]> {
    try {
      console.log('Fetching all plots from API...');
      const response = await this.fetchWithErrorHandling(`${API_BASE_URL}/api/plots`);
      const data = await response.json();
      
      console.log('Raw API response:', data);
      
      if (!data || typeof data !== 'object') {
        throw new Error('Invalid response format from server');
      }
      
      if (data.type !== 'FeatureCollection') {
        throw new Error('Expected GeoJSON FeatureCollection format');
      }
      
      if (!Array.isArray(data.features)) {
        throw new Error('Invalid features array in response');
      }
      
      // Transform GeoJSON features to Plot objects
      const plots: Plot[] = data.features.map((feature: any, index: number) => {
        try {
          if (!feature.properties || !feature.geometry) {
            console.warn(`Feature ${index} missing properties or geometry:`, feature);
            return null;
          }
          
          const props = feature.properties;
          
          // Validate required properties
          if (!props.id || !props.plot_code) {
            console.warn(`Feature ${index} missing required properties:`, props);
            return null;
          }
          
          // Validate geometry
          if (!feature.geometry.coordinates || feature.geometry.coordinates.length === 0) {
            console.warn(`Feature ${index} has invalid geometry:`, feature.geometry);
            return null;
          }
          
          return {
            id: props.id,
            plot_code: props.plot_code,
            status: props.status || 'available',
            area_hectares: parseFloat(props.area_hectares) || 0,
            district: props.district || 'Unknown',
            ward: props.ward || 'Unknown',
            village: props.village || 'Unknown',
            geometry: feature.geometry,
            attributes: props.attributes || {},
            created_at: props.created_at || new Date().toISOString(),
            updated_at: props.updated_at || new Date().toISOString(),
          };
        } catch (error) {
          console.error(`Error processing feature ${index}:`, error, feature);
          return null;
        }
      }).filter(Boolean); // Remove null entries
      
      console.log(`Successfully processed ${plots.length} plots from ${data.features.length} features`);
      
      if (plots.length === 0) {
        console.warn('No valid plots found in API response');
      }
      
      return plots;
      
    } catch (error) {
      console.error('Error fetching plots:', error);
      throw new Error(`Failed to load land plots: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async getPlotById(plotId: string): Promise<Plot | null> {
    try {
      console.log(`Fetching plot ${plotId}...`);
      const response = await this.fetchWithErrorHandling(`${API_BASE_URL}/api/plots/${plotId}`);
      const feature = await response.json();
      
      if (!feature.properties || !feature.geometry) {
        return null;
      }
      
      const props = feature.properties;
      return {
        id: props.id,
        plot_code: props.plot_code,
        status: props.status,
        area_hectares: parseFloat(props.area_hectares),
        district: props.district,
        ward: props.ward,
        village: props.village,
        geometry: feature.geometry,
        attributes: props.attributes || {},
        created_at: props.created_at,
        updated_at: props.updated_at,
      };
      
    } catch (error) {
      console.error(`Error fetching plot ${plotId}:`, error);
      return null;
    }
  }

  async createOrder(plotId: string, orderData: OrderData): Promise<Order> {
    try {
      console.log(`Creating order for plot ${plotId}:`, orderData);
      
      // Validate order data
      if (!orderData.customer_name?.trim()) {
        throw new Error('Customer name is required');
      }
      
      if (!orderData.customer_phone?.trim()) {
        throw new Error('Customer phone is required');
      }
      
      if (!orderData.customer_id_number?.trim()) {
        throw new Error('Customer ID number is required');
      }
      
      if (!orderData.intended_use) {
        throw new Error('Intended use is required');
      }
      
      const response = await this.fetchWithErrorHandling(
        `${API_BASE_URL}/api/plots/${plotId}/order`,
        {
          method: 'POST',
          body: JSON.stringify(orderData),
        }
      );
      
      const order = await response.json();
      console.log('Order created successfully:', order);
      
      return order;
      
    } catch (error) {
      console.error(`Error creating order for plot ${plotId}:`, error);
      throw new Error(`Failed to create order: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async searchPlots(filters: {
    district?: string;
    ward?: string;
    village?: string;
    status?: string;
    min_area?: number;
    max_area?: number;
    bbox?: string;
  }): Promise<Plot[]> {
    try {
      const params = new URLSearchParams();
      
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.append(key, value.toString());
        }
      });
      
      const url = `${API_BASE_URL}/api/plots/search?${params.toString()}`;
      console.log(`Searching plots with filters:`, filters);
      
      const response = await this.fetchWithErrorHandling(url);
      const data = await response.json();
      
      if (data.type !== 'FeatureCollection') {
        throw new Error('Expected GeoJSON FeatureCollection format');
      }
      
      // Transform features to plots (same logic as getAllPlots)
      const plots: Plot[] = data.features.map((feature: any) => {
        const props = feature.properties;
        return {
          id: props.id,
          plot_code: props.plot_code,
          status: props.status,
          area_hectares: parseFloat(props.area_hectares),
          district: props.district,
          ward: props.ward,
          village: props.village,
          geometry: feature.geometry,
          attributes: props.attributes || {},
          created_at: props.created_at,
          updated_at: props.updated_at,
        };
      });
      
      console.log(`Found ${plots.length} plots matching search criteria`);
      return plots;
      
    } catch (error) {
      console.error('Error searching plots:', error);
      throw new Error(`Failed to search plots: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async getSystemStats(): Promise<{
    total_plots: number;
    available_plots: number;
    taken_plots: number;
    pending_plots: number;
    total_orders: number;
    districts: number;
    wards: number;
    villages: number;
    total_area_hectares: number;
  }> {
    try {
      console.log('Fetching system statistics...');
      const response = await this.fetchWithErrorHandling(`${API_BASE_URL}/api/stats`);
      const stats = await response.json();
      
      console.log('System stats:', stats);
      return stats;
      
    } catch (error) {
      console.error('Error fetching system stats:', error);
      throw new Error(`Failed to fetch statistics: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async getOrders(filters?: {
    status?: string;
    plot_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<{
    orders: Order[];
    total: number;
  }> {
    try {
      const params = new URLSearchParams();
      
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== undefined && value !== null && value !== '') {
            params.append(key, value.toString());
          }
        });
      }
      
      const url = `${API_BASE_URL}/api/orders?${params.toString()}`;
      console.log('Fetching orders...');
      
      const response = await this.fetchWithErrorHandling(url);
      const data = await response.json();
      
      console.log(`Fetched ${data.orders?.length || 0} orders`);
      return data;
      
    } catch (error) {
      console.error('Error fetching orders:', error);
      throw new Error(`Failed to fetch orders: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  // Health check method
  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }
}

// Export singleton instance
export const plotService = new PlotService();
export default plotService;