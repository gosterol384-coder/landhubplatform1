// Simple test script to verify backend API is working
const API_BASE_URL = 'http://localhost:8000';

async function testAPI() {
  console.log('Testing backend API connection...');
  
  try {
    // Test health endpoint
    console.log('1. Testing health endpoint...');
    const healthResponse = await fetch(`${API_BASE_URL}/health`);
    console.log('Health status:', healthResponse.status);
    const healthData = await healthResponse.json();
    console.log('Health data:', healthData);
    
    // Test plots endpoint
    console.log('2. Testing plots endpoint...');
    const plotsResponse = await fetch(`${API_BASE_URL}/api/plots`);
    console.log('Plots status:', plotsResponse.status);
    const plotsData = await plotsResponse.json();
    console.log('Plots data type:', plotsData.type);
    console.log('Number of features:', plotsData.features?.length || 0);
    
    if (plotsData.features && plotsData.features.length > 0) {
      console.log('Sample plot:', plotsData.features[0]);
    }
    
    console.log('✅ Backend API is working correctly!');
    
  } catch (error) {
    console.error('❌ Backend API test failed:', error);
    console.log('Make sure the backend is running on port 8000');
  }
}

// Run the test
testAPI();