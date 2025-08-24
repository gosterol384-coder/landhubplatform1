import React, { useEffect, useState, useRef, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import PlotOrderModal from './PlotOrderModal';
import { Plot, OrderData } from '../types/land';
import { plotService } from '../services/plotService';
import LoadingSpinner from './LoadingSpinner';

// Fix for default markers in Leaflet with Vite - Critical for proper icon rendering
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// Tanzania bounds for validation
const TANZANIA_BOUNDS = {
  north: -0.95,
  south: -11.75,
  east: 40.44,
  west: 29.34
};
const MapView: React.FC = () => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const plotLayerRef = useRef<L.GeoJSON | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  
  const [plots, setPlots] = useState<Plot[]>([]);
  const [selectedPlot, setSelectedPlot] = useState<Plot | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mapInitialized, setMapInitialized] = useState(false);
  const [tilesLoaded, setTilesLoaded] = useState(false);
  const [mapCenter, setMapCenter] = useState<[number, number]>([-6.369028, 34.888822]);
  const [mapZoom, setMapZoom] = useState(8);

  // Enhanced map initialization with better Tanzania-specific configuration
  const initializeMap = useCallback(() => {
    if (!mapRef.current || mapInstanceRef.current) {
      console.log('Map already initialized or container not ready');
      return;
    }

    console.log('Initializing Leaflet map...');

    try {
      // Create map with enhanced Tanzania-specific settings
      const map = L.map(mapRef.current, {
        center: mapCenter,
        zoom: mapZoom,
        minZoom: 2,
        maxZoom: 19,
        zoomControl: true,
        attributionControl: true,
        preferCanvas: true, // Better performance for large datasets
        worldCopyJump: true, // Handle world wrapping
        // Set reasonable bounds for Tanzania region
        maxBounds: [
          [TANZANIA_BOUNDS.south - 2, TANZANIA_BOUNDS.west - 2],
          [TANZANIA_BOUNDS.north + 2, TANZANIA_BOUNDS.east + 2]
        ],
        maxBoundsViscosity: 0.5, // Allow some dragging outside bounds
      });

      // Enhanced OpenStreetMap tile layer with multiple fallback servers
      const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Tanzania Land Registry',
        maxZoom: 19,
        minZoom: 1,
        subdomains: ['a', 'b', 'c'], // Use multiple subdomains for better performance
        crossOrigin: true,
        // Enhanced error handling with custom error tile
        errorTileUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjU2IiBoZWlnaHQ9IjI1NiIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjU2IiBoZWlnaHQ9IjI1NiIgZmlsbD0iI2Y0ZjRmNCIgc3Ryb2tlPSIjZGRkIiBzdHJva2Utd2lkdGg9IjEiLz48dGV4dCB4PSI1MCUiIHk9IjUwJSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZm9udC1mYW1pbHk9InNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTJweCIgZmlsbD0iIzk5OSI+TWFwIFRpbGU8L3RleHQ+PC9zdmc+',
        // Optimized loading settings
        keepBuffer: 2,
        updateWhenIdle: false,
        updateWhenZooming: false,
      });

      // Comprehensive tile loading event handlers
      osmLayer.on('loading', () => {
        console.log('OSM tiles loading...');
        setTilesLoaded(false);
      });

      osmLayer.on('load', () => {
        console.log('OSM tiles loaded successfully');
        setTilesLoaded(true);
      });

      osmLayer.on('tileerror', (e: any) => {
        console.warn('OSM tile loading error (non-critical):', e.tile.src);
      });

      // Add tile layer to map
      osmLayer.addTo(map);
      tileLayerRef.current = osmLayer;

      // Enhanced map event handlers
      map.on('zoomend', () => {
        const zoom = map.getZoom();
        setMapZoom(zoom);
        console.log(`Map zoom level: ${zoom}`);
      });

      map.on('moveend', () => {
        const center = map.getCenter();
        setMapCenter([center.lat, center.lng]);
        console.log(`Map center: ${center.lat.toFixed(6)}, ${center.lng.toFixed(6)}`);
      });

      map.on('click', (e) => {
        console.log(`Map clicked at: ${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`);
        // Close any open popups when clicking on empty map
        map.closePopup();
      });

      // Add scale control
      L.control.scale({
        position: 'bottomleft',
        metric: true,
        imperial: false
      }).addTo(map);

      // Store map instance and mark as initialized
      mapInstanceRef.current = map;
      setMapInitialized(true);
      
      console.log('Map initialized successfully');

      // Force a resize to ensure proper rendering
      setTimeout(() => {
        map.invalidateSize();
      }, 100);

    } catch (error) {
      console.error('Error initializing map:', error);
      setError('Failed to initialize map. Please refresh the page.');
    }
  }, []);

  // Enhanced plot loading with better error handling and validation
  const loadPlots = useCallback(async () => {
    if (!mapInitialized) {
      console.log('Map not initialized yet, skipping plot loading');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      console.log('Loading plots from API...');
      
      const plotsData = await plotService.getAllPlots();
      console.log(`Loaded ${plotsData.length} plots from API`);
      
      if (plotsData.length === 0) {
        console.warn('No plots received from API');
        setError('No land plots available to display');
        return;
      }
      
      // Validate plot data before setting state
      const validPlots = plotsData.filter(plot => {
        if (!plot.id || !plot.plot_code) {
          console.warn('Plot missing required fields:', plot);
          return false;
        }
        if (!plot.geometry || !plot.geometry.coordinates) {
          console.warn(`Plot ${plot.plot_code} has invalid geometry`);
          return false;
        }
        return true;
        // Validate coordinates are within reasonable Tanzania bounds
        try {
          const coords = plot.geometry.coordinates;
          let hasValidCoords = false;
          
          if (plot.geometry.type === 'Polygon') {
            hasValidCoords = coords[0].some((coord: number[]) => 
              coord[0] >= TANZANIA_BOUNDS.west && coord[0] <= TANZANIA_BOUNDS.east &&
              coord[1] >= TANZANIA_BOUNDS.south && coord[1] <= TANZANIA_BOUNDS.north
            );
          } else if (plot.geometry.type === 'MultiPolygon') {
            hasValidCoords = coords[0][0].some((coord: number[]) => 
              coord[0] >= TANZANIA_BOUNDS.west && coord[0] <= TANZANIA_BOUNDS.east &&
              coord[1] >= TANZANIA_BOUNDS.south && coord[1] <= TANZANIA_BOUNDS.north
            );
          }
          
          if (!hasValidCoords) {
            console.warn(`Plot ${plot.plot_code} coordinates outside Tanzania bounds`);
            return false;
          }
        } catch (e) {
          console.warn(`Error validating coordinates for plot ${plot.plot_code}:`, e);
          return false;
        }
        
      });

      console.log(`${validPlots.length} valid plots after validation`);
      
      setPlots(validPlots);
      
      // Render plots on map with delay to ensure map is ready
      setTimeout(() => {
        renderPlotsOnMap(validPlots);
      }, 100);
      
    } catch (err) {
      console.error('Error loading plots:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to load land plots: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  }, [mapInitialized]);

  // Enhanced plot rendering with comprehensive error handling and validation
  const renderPlotsOnMap = useCallback((plotsData: Plot[]) => {
    console.log(`Attempting to render ${plotsData.length} plots on map`);
    
    if (!mapInstanceRef.current) {
      console.error('Map instance not available for rendering plots');
      
      // Attempt to reinitialize map if missing
      if (mapRef.current && !mapInstanceRef.current) {
        console.log('Attempting to reinitialize map...');
        initializeMap();
        
        // Retry after reinitialization
        setTimeout(() => {
          if (mapInstanceRef.current) {
            renderPlotsOnMap(plotsData);
          }
        }, 1000);
      }
      return;
    }

    // Remove existing plot layer
    if (plotLayerRef.current) {
      console.log('Removing existing plot layer');
      mapInstanceRef.current.removeLayer(plotLayerRef.current);
      plotLayerRef.current = null;
    }

    if (plotsData.length === 0) {
      console.error('No valid plots to render after validation');
      setError('No valid plot geometries found');
      return;
    }

    console.log(`Rendering ${plotsData.length} plots`);

    // Convert plots to proper GeoJSON format with enhanced structure
    const geoJsonData = {
      type: 'FeatureCollection' as const,
      features: plotsData.map(plot => {
        // Ensure geometry is properly formatted for Leaflet
        let geometry = plot.geometry;
        
        // Convert Polygon to MultiPolygon for consistency
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
            village: plot.village,
            attributes: plot.attributes || {},
            created_at: plot.created_at,
            updated_at: plot.updated_at
          },
          geometry: geometry
        };
      })
    };

    console.log('GeoJSON data prepared:', {
      type: geoJsonData.type,
      featureCount: geoJsonData.features.length,
      sampleFeature: geoJsonData.features[0]?.properties
    });

    try {
      // Create enhanced plot layer with comprehensive styling
      plotLayerRef.current = L.geoJSON(geoJsonData, {
        style: (feature) => {
          const status = feature?.properties?.status || 'available';
          return {
            fillColor: getPlotColor(status),
            weight: 2,
            opacity: 1,
            color: '#ffffff',
            fillOpacity: 0.7,
            dashArray: status === 'pending' ? '5, 5' : undefined,
            // Enhanced visual feedback
            className: `plot-${status}`
          };
        },
        onEachFeature: (feature, layer) => {
          const plotId = feature.properties.id;
          const plotCode = feature.properties.plot_code;
          
          // Enhanced hover effects with smooth transitions
          layer.on({
            mouseover: (e) => {
              const layer = e.target;
              layer.setStyle({
                weight: 4,
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
              console.log(`Plot clicked: ${plotCode} (${plotId})`);
              handlePlotClick(plotId);
              
              // Prevent event bubbling
              L.DomEvent.stopPropagation(e);
            }
          });

          // Enhanced popup with comprehensive plot information
          const popupContent = `
            <div class="plot-popup p-4 min-w-[250px] max-w-[300px]">
              <div class="popup-header mb-3">
                <h3 class="font-bold text-lg text-gray-800 mb-1">${feature.properties.plot_code}</h3>
                <span class="inline-block px-2 py-1 rounded-full text-xs font-semibold ${getStatusBadgeClass(feature.properties.status)}">
                  ${feature.properties.status.toUpperCase()}
                </span>
              </div>
              
              <div class="popup-details space-y-2 text-sm text-gray-600 mb-4">
                <div class="flex justify-between">
                  <span class="font-medium">Area:</span>
                  <span>${feature.properties.area_hectares} hectares</span>
                </div>
                <div class="flex justify-between">
                  <span class="font-medium">District:</span>
                  <span>${feature.properties.district}</span>
                </div>
                <div class="flex justify-between">
                  <span class="font-medium">Ward:</span>
                  <span>${feature.properties.ward}</span>
                </div>
                <div class="flex justify-between">
                  <span class="font-medium">Village:</span>
                  <span>${feature.properties.village}</span>
                </div>
                ${feature.properties.attributes && Object.keys(feature.properties.attributes).length > 0 ? 
                  `<div class="mt-2 pt-2 border-t border-gray-200">
                    <span class="font-medium text-xs text-gray-500">Additional Attributes:</span>
                    ${Object.entries(feature.properties.attributes).slice(0, 3).map(([key, value]) => 
                      `<div class="flex justify-between text-xs">
                        <span>${key}:</span>
                        <span>${value}</span>
                      </div>`
                    ).join('')}
                  </div>` : ''
                }
              </div>
              
              <div class="popup-actions">
                ${feature.properties.status === 'available' ? 
                  `<button 
                    onclick="window.openOrderModal('${plotId}')" 
                    class="w-full px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition-colors font-medium shadow-sm"
                  >
                    Order This Plot
                  </button>` : 
                  `<div class="text-center py-2">
                    <span class="text-sm font-medium ${
                      feature.properties.status === 'taken' ? 'text-red-600' : 'text-yellow-600'
                    }">
                      ${feature.properties.status === 'taken' ? 'This plot is not available' : 'Order pending approval'}
                    </span>
                  </div>`
                }
              </div>
            </div>
          `;

          layer.bindPopup(popupContent, {
            maxWidth: 320,
            className: 'custom-popup',
            closeButton: true,
            autoPan: true,
            keepInView: true
          });
        },
        // Enhanced coordinate precision for better rendering
        coordsToLatLng: (coords) => {
          return new L.LatLng(coords[1], coords[0], coords[2]);
        }
      });

      // Add layer to map with error handling
      if (mapInstanceRef.current && plotLayerRef.current) {
        plotLayerRef.current.addTo(mapInstanceRef.current);
        console.log('Plot layer added to map successfully');

        // Smart map bounds fitting
        const bounds = plotLayerRef.current.getBounds();
        if (bounds.isValid()) {
          // Only fit bounds if plots are clustered in a small area
          const boundsSize = bounds.getNorthEast().distanceTo(bounds.getSouthWest());
          if (boundsSize < 100000) { // Less than 100km
            const padding = Math.max(20, Math.min(100, window.innerWidth * 0.1));
            mapInstanceRef.current.fitBounds(bounds, { 
              padding: [padding, padding],
              maxZoom: 15
            });
          } else {
            // For widely distributed plots, use a reasonable Tanzania view
            mapInstanceRef.current.setView([-6.369028, 34.888822], 8);
          }
          console.log('Map fitted to plot bounds:', bounds);
        } else {
          console.warn('Invalid bounds, using default Tanzania view');
          mapInstanceRef.current.setView([-6.369028, 34.888822], 8);
        }
      }

    } catch (error) {
      console.error('Error creating plot layer:', error);
      setError('Failed to render plots on map. Please try refreshing the page.');
    }
  }, []);

  // Enhanced plot color scheme with better accessibility
  const getPlotColor = (status: string): string => {
    switch (status) {
      case 'available':
        return '#10B981'; // green-500 - Available plots
      case 'taken':
        return '#EF4444'; // red-500 - Taken plots
      case 'pending':
        return '#F59E0B'; // amber-500 - Pending plots
      default:
        return '#6B7280'; // gray-500 - Unknown status
    }
  };

  // Enhanced status badge styling
  const getStatusBadgeClass = (status: string): string => {
    switch (status) {
      case 'available':
        return 'bg-green-100 text-green-800 border border-green-200';
      case 'taken':
        return 'bg-red-100 text-red-800 border border-red-200';
      case 'pending':
        return 'bg-yellow-100 text-yellow-800 border border-yellow-200';
      default:
        return 'bg-gray-100 text-gray-800 border border-gray-200';
    }
  };

  // Enhanced plot click handler
  const handlePlotClick = useCallback((plotId: string) => {
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
  }, [plots]);

  // Enhanced order submission with optimistic updates
  const handleOrderSubmit = async (orderData: OrderData) => {
    if (!selectedPlot) return;

    try {
      console.log('Submitting order for plot:', selectedPlot.plot_code);
      await plotService.createOrder(selectedPlot.id, orderData);
      
      // Optimistic update - immediately update local state
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
      
      // Show success message
      alert(`Order submitted successfully for plot ${selectedPlot.plot_code}! The plot status has been updated to pending.`);
      
    } catch (err) {
      console.error('Error creating order:', err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      alert(`Failed to submit order: ${errorMessage}. Please try again.`);
    }
  };

  // Initialize map on component mount
  useEffect(() => {
    console.log('MapView component mounted');
    
    // Small delay to ensure DOM is ready
    const initTimer = setTimeout(() => {
      initializeMap();
    }, 100);

    return () => {
      clearTimeout(initTimer);
      // Cleanup map instance on unmount
      if (mapInstanceRef.current) {
        console.log('Cleaning up map instance');
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [initializeMap]);

  // Load plots when map is initialized
  useEffect(() => {
    if (mapInitialized) {
      console.log('Map initialized, loading plots...');
      loadPlots();
    }
  }, [mapInitialized, loadPlots]);

  // Make openOrderModal available globally for popup buttons
  useEffect(() => {
    (window as any).openOrderModal = (plotId: string) => {
      console.log('Opening order modal for plot:', plotId);
      handlePlotClick(plotId);
    };
    
    return () => {
      delete (window as any).openOrderModal;
    };
  }, [handlePlotClick]);

  // Loading state
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <LoadingSpinner />
          <div className="mt-4 space-y-2">
            <p className="text-sm text-gray-600">
              {!mapInitialized ? 'Initializing map...' : 
               !tilesLoaded ? 'Loading map tiles...' : 
               'Loading plot data...'}
            </p>
            <div className="flex items-center justify-center space-x-2 text-xs text-gray-500">
              <div className={`w-2 h-2 rounded-full ${mapInitialized ? 'bg-green-500' : 'bg-gray-300'}`}></div>
              <span>Map</span>
              <div className={`w-2 h-2 rounded-full ${tilesLoaded ? 'bg-green-500' : 'bg-gray-300'}`}></div>
              <span>Tiles</span>
              <div className={`w-2 h-2 rounded-full ${plots.length > 0 ? 'bg-green-500' : 'bg-gray-300'}`}></div>
              <span>Plots</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50">
        <div className="text-center p-8 max-w-md">
          <div className="mb-4 text-red-600">
            <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">System Error</h3>
          <p className="text-red-600 mb-4 font-medium">{error}</p>
          <div className="space-y-2">
            <button 
              onClick={() => {
                setError(null);
                setLoading(true);
                initializeMap();
              }}
              className="w-full px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium"
            >
              Retry System
            </button>
            <button 
              onClick={() => {
                setError(null);
                loadPlots();
              }}
              className="w-full px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Reload Data Only
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div 
        ref={mapRef} 
        className="h-full w-full relative bg-gray-100"
        style={{ 
          minHeight: '400px',
          // Ensure proper rendering context
          position: 'relative',
          zIndex: 0
        }}
      />
      
      {/* Plot count indicator */}
      {plots.length > 0 && (
        <div className="absolute top-4 right-4 bg-white rounded-lg shadow-lg px-3 py-2 z-[1000]">
          <div className="text-sm font-medium text-gray-700">
            {plots.length} plots loaded
          </div>
          <div className="text-xs text-gray-500 space-x-2">
            <span className="inline-flex items-center">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-1"></div>
              {plots.filter(p => p.status === 'available').length} available
            </span>
            <span className="inline-flex items-center">
              <div className="w-2 h-2 bg-red-500 rounded-full mr-1"></div>
              {plots.filter(p => p.status === 'taken').length} taken
            </span>
            <span className="inline-flex items-center">
              <div className="w-2 h-2 bg-yellow-500 rounded-full mr-1"></div>
              {plots.filter(p => p.status === 'pending').length} pending
            </span>
          </div>
        </div>
      )}
      
      {/* Order Modal */}
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