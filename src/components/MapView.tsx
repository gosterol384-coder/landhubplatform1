import React, { useEffect, useState, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import PlotOrderModal from './PlotOrderModal';
import { Plot, OrderData } from '../types/land';
import { plotService } from '../services/plotService';
import LoadingSpinner from './LoadingSpinner';

// Fix for default markers in Leaflet with Vite
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

const MapView: React.FC = () => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const plotLayerRef = useRef<L.GeoJSON | null>(null);
  
  const [plots, setPlots] = useState<Plot[]>([]);
  const [selectedPlot, setSelectedPlot] = useState<Plot | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    initializeMap();
    loadPlots();

    // Cleanup map instance on unmount
    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  const initializeMap = () => {
    if (!mapRef.current || mapInstanceRef.current) return;

    console.log('Initializing map...');

    // Initialize map centered on Tanzania with proper zoom level
    const map = L.map(mapRef.current, {
      center: [-6.369028, 34.888822], // Tanzania center coordinates
      zoom: 8,
      zoomControl: true,
      attributionControl: true
    });

    // Add OpenStreetMap tiles with proper configuration
    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
      minZoom: 1,
      crossOrigin: true, // Important for CORS
      // Add error handling for tile loading
      errorTileUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
    });

    // Add tile layer to map and handle load events
    osmLayer.addTo(map);
    
    // Debug tile loading
    osmLayer.on('loading', () => {
      console.log('Tiles are loading...');
    });
    
    osmLayer.on('load', () => {
      console.log('Tiles loaded successfully');
    });
    
    osmLayer.on('tileerror', (e) => {
      console.error('Tile loading error:', e);
    });

    // Store map instance
    mapInstanceRef.current = map;
    
    console.log('Map initialized successfully');
  };

  const loadPlots = async () => {
    try {
      setLoading(true);
      setError(null);
      console.log('Loading plots from API...');
      
      const plotsData = await plotService.getAllPlots();
      console.log('Loaded plots:', plotsData.length, plotsData);
      
      if (plotsData.length === 0) {
        console.warn('No plots received from API');
        setError('No land plots available to display');
        return;
      }
      
      setPlots(plotsData);
      renderPlotsOnMap(plotsData);
    } catch (err) {
      console.error('Error loading plots:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to load land plots: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  };

  const renderPlotsOnMap = (plotsData: Plot[]) => {
    if (!mapInstanceRef.current) {
      console.error('Map instance not available for rendering plots');
      return;
    }

    console.log('Rendering plots on map:', plotsData.length);

    // Remove existing plot layer
    if (plotLayerRef.current) {
      mapInstanceRef.current.removeLayer(plotLayerRef.current);
      plotLayerRef.current = null;
    }

    // Validate plot data before rendering
    const validPlots = plotsData.filter(plot => {
      if (!plot.geometry) {
        console.warn(`Plot ${plot.plot_code} has no geometry, skipping`);
        return false;
      }
      if (!plot.geometry.coordinates || plot.geometry.coordinates.length === 0) {
        console.warn(`Plot ${plot.plot_code} has invalid coordinates, skipping`);
        return false;
      }
      return true;
    });

    if (validPlots.length === 0) {
      console.error('No valid plots to render');
      setError('No valid plot geometries found');
      return;
    }

    // Convert plots to proper GeoJSON format
    const geoJsonData = {
      type: 'FeatureCollection' as const,
      features: validPlots.map(plot => {
        // Ensure geometry is properly formatted
        let geometry = plot.geometry;
        
        // Convert Polygon to MultiPolygon if needed for consistency
        if (geometry.type === 'Polygon') {
          geometry = {
            type: 'MultiPolygon',
            coordinates: [geometry.coordinates]
          };
        }

        return {
          type: 'Feature' as const,
          properties: {
            id: plot.id,
            plot_code: plot.plot_code,
            status: plot.status,
            area_hectares: plot.area_hectares,
            district: plot.district,
            ward: plot.ward,
            village: plot.village
          },
          geometry: geometry
        };
      })
    };

    console.log('GeoJSON data prepared:', {
      type: geoJsonData.type,
      featureCount: geoJsonData.features.length,
      firstFeature: geoJsonData.features[0]
    });

    // Create plot layer with enhanced styling and error handling
    try {
      plotLayerRef.current = L.geoJSON(geoJsonData, {
        style: (feature) => {
          const status = feature?.properties?.status || 'available';
          return {
            fillColor: getPlotColor(status),
            weight: 2,
            opacity: 1,
            color: '#ffffff',
            fillOpacity: 0.7,
            // Add stroke for better visibility
            dashArray: status === 'pending' ? '5, 5' : undefined
          };
        },
        onEachFeature: (feature, layer) => {
          const plotId = feature.properties.id;
          
          // Add hover effects
          layer.on({
            mouseover: (e) => {
              const layer = e.target;
              layer.setStyle({
                weight: 3,
                fillOpacity: 0.9,
                color: '#000000'
              });
              
              // Bring to front for better visibility
              if (layer.bringToFront) {
                layer.bringToFront();
              }
            },
            mouseout: (e) => {
              if (plotLayerRef.current) {
                plotLayerRef.current.resetStyle(e.target);
              }
            },
            click: (e) => {
              console.log('Plot clicked:', plotId);
              handlePlotClick(plotId);
              
              // Prevent event bubbling
              L.DomEvent.stopPropagation(e);
            }
          });

          // Create enhanced popup with better styling
          const popupContent = `
            <div class="p-3 min-w-[200px]">
              <h3 class="font-bold text-lg text-gray-800 mb-2">${feature.properties.plot_code}</h3>
              <div class="space-y-1 text-sm text-gray-600 mb-3">
                <p><span class="font-medium">Area:</span> ${feature.properties.area_hectares} hectares</p>
                <p><span class="font-medium">District:</span> ${feature.properties.district}</p>
                <p><span class="font-medium">Ward:</span> ${feature.properties.ward}</p>
                <p><span class="font-medium">Village:</span> ${feature.properties.village}</p>
                <p><span class="font-medium">Status:</span> 
                  <span class="font-semibold capitalize px-2 py-1 rounded text-xs ${getStatusBadgeClass(feature.properties.status)}">
                    ${feature.properties.status}
                  </span>
                </p>
              </div>
              ${feature.properties.status === 'available' ? 
                `<button 
                  onclick="window.openOrderModal('${plotId}')" 
                  class="w-full px-3 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700 transition-colors font-medium"
                >
                  Order This Plot
                </button>` : 
                `<p class="text-sm text-red-600 font-medium text-center py-2">This plot is not available</p>`
              }
            </div>
          `;

          layer.bindPopup(popupContent, {
            maxWidth: 250,
            className: 'custom-popup'
          });
        }
      });

      // Add layer to map
      plotLayerRef.current.addTo(mapInstanceRef.current);
      console.log('Plot layer added to map successfully');

      // Fit map to plots bounds with padding
      const bounds = plotLayerRef.current.getBounds();
      if (bounds.isValid()) {
        mapInstanceRef.current.fitBounds(bounds, { 
          padding: [20, 20],
          maxZoom: 15 // Prevent zooming too close
        });
        console.log('Map fitted to plot bounds:', bounds);
      } else {
        console.warn('Invalid bounds, using default Tanzania view');
        mapInstanceRef.current.setView([-6.369028, 34.888822], 8);
      }

    } catch (error) {
      console.error('Error creating plot layer:', error);
      setError('Failed to render plots on map');
    }
  };

  const getPlotColor = (status: string): string => {
    switch (status) {
      case 'available':
        return '#10B981'; // green-500
      case 'taken':
        return '#EF4444'; // red-500
      case 'pending':
        return '#F59E0B'; // amber-500
      default:
        return '#6B7280'; // gray-500
    }
  };

  const getStatusBadgeClass = (status: string): string => {
    switch (status) {
      case 'available':
        return 'bg-green-100 text-green-800';
      case 'taken':
        return 'bg-red-100 text-red-800';
      case 'pending':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const handlePlotClick = (plotId: string) => {
    console.log('Handling plot click for ID:', plotId);
    const plot = plots.find(p => p.id === plotId);
    if (plot && plot.status === 'available') {
      setSelectedPlot(plot);
      setIsModalOpen(true);
    } else if (plot) {
      console.log(`Plot ${plot.plot_code} is not available (status: ${plot.status})`);
    } else {
      console.error('Plot not found:', plotId);
    }
  };

  const handleOrderSubmit = async (orderData: OrderData) => {
    if (!selectedPlot) return;

    try {
      console.log('Submitting order for plot:', selectedPlot.plot_code);
      await plotService.createOrder(selectedPlot.id, orderData);
      
      // Update local state
      const updatedPlots = plots.map(plot => 
        plot.id === selectedPlot.id 
          ? { ...plot, status: 'pending' as const }
          : plot
      );
      
      setPlots(updatedPlots);

      // Re-render map with updated status
      renderPlotsOnMap(updatedPlots);

      setIsModalOpen(false);
      setSelectedPlot(null);
      
      console.log('Order submitted successfully');
    } catch (err) {
      console.error('Error creating order:', err);
      alert('Failed to submit order. Please try again.');
    }
  };

  // Make openOrderModal available globally for popup button
  useEffect(() => {
    (window as any).openOrderModal = (plotId: string) => {
      console.log('Opening order modal for plot:', plotId);
      handlePlotClick(plotId);
    };
    
    return () => {
      delete (window as any).openOrderModal;
    };
  }, [plots]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-center p-8 max-w-md">
          <div className="mb-4 text-red-600">
            <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <p className="text-red-600 mb-4 font-medium">{error}</p>
          <button 
            onClick={loadPlots}
            className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium"
          >
            Retry Loading
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div 
        ref={mapRef} 
        className="h-full w-full relative"
        style={{ minHeight: '400px' }} // Ensure minimum height for map
      />
      
      {isModalOpen && selectedPlot && (
        <PlotOrderModal
          plot={selectedPlot}
          onClose={() => {
            setIsModalOpen(false);
            setSelectedPlot(null);
          }}
          onSubmit={handleOrderSubmit}
        />
      )}
    </>
  );
};

export default MapView;