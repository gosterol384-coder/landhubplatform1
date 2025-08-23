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

    // Initialize map centered on Tanzania
    const map = L.map(mapRef.current).setView([-6.369028, 34.888822], 8);

    // Add OpenStreetMap tiles only if not already added
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    mapInstanceRef.current = map;
  };

  const loadPlots = async () => {
    try {
      setLoading(true);
      setError(null);
      const plotsData = await plotService.getAllPlots();
      console.log('Loaded plots:', plotsData.length);
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
    if (!mapInstanceRef.current) return;

    console.log('Rendering plots on map:', plotsData.length);

    // Remove existing plot layer
    if (plotLayerRef.current) {
      mapInstanceRef.current.removeLayer(plotLayerRef.current);
    }

    // Convert plots to GeoJSON format
    const geoJsonData = {
      type: 'FeatureCollection' as const,
      features: plotsData.map(plot => ({
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
        geometry: plot.geometry
      }))
    };

    // Create plot layer with styling
    plotLayerRef.current = L.geoJSON(geoJsonData, {
      style: (feature) => {
        const status = feature?.properties?.status || 'available';
        return {
          fillColor: getPlotColor(status),
          weight: 2,
          opacity: 1,
          color: '#ffffff',
          fillOpacity: 0.7
        };
      },
      onEachFeature: (feature, layer) => {
        // Add hover effects
        layer.on({
          mouseover: (e) => {
            const layer = e.target;
            layer.setStyle({
              weight: 3,
              fillOpacity: 0.9
            });
          },
          mouseout: (e) => {
            plotLayerRef.current?.resetStyle(e.target);
          },
          click: (e) => {
            handlePlotClick(feature.properties.id);
          }
        });

        // Bind popup with plot information
        layer.bindPopup(`
          <div class="p-2">
            <h3 class="font-bold text-lg">${feature.properties.plot_code}</h3>
            <p class="text-sm text-gray-600">Area: ${feature.properties.area_hectares} hectares</p>
            <p class="text-sm text-gray-600">District: ${feature.properties.district}</p>
            <p class="text-sm text-gray-600">Status: <span class="font-semibold capitalize">${feature.properties.status}</span></p>
            ${feature.properties.status === 'available' ? 
              '<button class="mt-2 px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700" onclick="window.openOrderModal()">Order This Plot</button>' : 
              '<p class="mt-2 text-sm text-red-600">This plot is not available</p>'
            }
          </div>
        `);
      }
    });

    plotLayerRef.current.addTo(mapInstanceRef.current);

    // Fit map to plots bounds
    if (plotsData.length > 0) {
      const bounds = plotLayerRef.current.getBounds();
      if (bounds.isValid()) {
        mapInstanceRef.current.fitBounds(bounds, { padding: [20, 20] });
        console.log('Map fitted to bounds:', bounds);
      } else {
        console.warn('Invalid bounds, using default Tanzania view');
        mapInstanceRef.current.setView([-6.369028, 34.888822], 8);
      }
    } else {
      console.warn('No plots to display, using default Tanzania view');
      mapInstanceRef.current.setView([-6.369028, 34.888822], 8);
    }
  };

  const getPlotColor = (status: string): string => {
    switch (status) {
      case 'available':
        return '#10B981'; // green
      case 'taken':
        return '#EF4444'; // red
      case 'pending':
        return '#F59E0B'; // yellow
      default:
        return '#6B7280'; // gray
    }
  };

  const handlePlotClick = (plotId: string) => {
    const plot = plots.find(p => p.id === plotId);
    if (plot && plot.status === 'available') {
      setSelectedPlot(plot);
      setIsModalOpen(true);
    }
  };

  const handleOrderSubmit = async (orderData: OrderData) => {
    if (!selectedPlot) return;

    try {
      await plotService.createOrder(selectedPlot.id, orderData);
      
      // Update local state
      setPlots(plots.map(plot => 
        plot.id === selectedPlot.id 
          ? { ...plot, status: 'pending' }
          : plot
      ));

      // Re-render map with updated status
      renderPlotsOnMap(plots.map(plot => 
        plot.id === selectedPlot.id 
          ? { ...plot, status: 'pending' }
          : plot
      ));

      setIsModalOpen(false);
      setSelectedPlot(null);
    } catch (err) {
      console.error('Error creating order:', err);
      alert('Failed to submit order. Please try again.');
    }
  };

  // Make openOrderModal available globally for popup button
  useEffect(() => {
    (window as any).openOrderModal = () => {
      if (selectedPlot && selectedPlot.status === 'available') {
        setIsModalOpen(true);
      }
    };
  }, [selectedPlot]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center p-8">
          <p className="text-red-600 mb-4">{error}</p>
          <button 
            onClick={loadPlots}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div ref={mapRef} className="h-full w-full" />
      
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