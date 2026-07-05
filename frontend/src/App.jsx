import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import Forecast from './pages/Forecast';
import Extraction from './pages/Extraction';

function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-gray-950">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/forecast" element={<Forecast />} />
            <Route path="/extract" element={<Extraction />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;