import React from 'react';
import MapView from './components/MapView';
import Header from './components/Header';
import './styles/globals.css';

function App() {
  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <Header />
      <div className="flex-1">
        <MapView />
      </div>
    </div>
  );
}

export default App;