import { useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from 'recharts';
import { generateForecast } from '../api/services';

export default function Forecast() {
  const [productId, setProductId] = useState('PROD-1000');
  const [horizon, setHorizon] = useState(14);
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleGenerate = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setForecast(null);
    try {
      const res = await generateForecast(productId, horizon);
      setForecast(res.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to generate forecast.');
    } finally {
      setLoading(false);
    }
  };

  // Safely format data for Recharts to prevent rendering crashes
  const getChartData = () => {
    if (!forecast || !forecast.points) return [];
    return forecast.points.map((p) => {
      const dateObj = new Date(p.date);
      const label = dateObj instanceof Date && !isNaN(dateObj) 
        ? dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) 
        : 'Unknown';
        
      return {
        name: label,
        Lower: Number(p.lower_bound) || 0,
        Demand: Number(p.predicted_demand) || 0,
        Upper: Number(p.upper_bound) || 0,
      };
    });
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Demand Forecasting</h2>
        <p className="text-gray-500 mt-1">Generate AI-powered demand predictions</p>
      </div>

      {/* Input Form */}
      <form onSubmit={handleGenerate} className="bg-gray-900 border border-gray-800 rounded-xl p-6 flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-sm text-gray-400 mb-2">Product ID</label>
          <input 
            type="text" 
            value={productId} 
            onChange={(e) => setProductId(e.target.value)} 
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white outline-none focus:border-blue-500"
            placeholder="e.g. PROD-1000"
          />
        </div>
        <div className="w-32">
          <label className="block text-sm text-gray-400 mb-2">Days Ahead</label>
          <input 
            type="number" 
            value={horizon} 
            onChange={(e) => setHorizon(parseInt(e.target.value) || 14)} 
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white outline-none focus:border-blue-500"
            min="7" max="90"
          />
        </div>
        <button 
          type="submit" 
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg font-medium disabled:opacity-50 transition-colors"
        >
          {loading ? 'Generating...' : 'Generate Forecast'}
        </button>
      </form>

      {/* Error Display */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/50 text-red-400 p-4 rounded-xl">
          {error}
        </div>
      )}

      {/* Results Area */}
      {forecast && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          
          {/* Chart Container - Uses explicit pixel height for Recharts */}
          <div className="lg:col-span-3 bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h3 className="text-lg font-semibold text-white mb-4">
              {forecast.product_name} - {forecast.horizon_days}-Day Prediction
            </h3>
            <div style={{ width: '100%', height: '350px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={getChartData()} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="name" stroke="#9CA3AF" fontSize={12} />
                  <YAxis stroke="#9CA3AF" fontSize={12} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#1F2937', 
                      border: '1px solid #374151', 
                      borderRadius: '8px',
                      color: '#fff' 
                    }} 
                  />
                  <Bar dataKey="Lower" fill="#1E3A5F" name="Lower Bound" />
                  <Bar dataKey="Demand" fill="#3B82F6" name="Predicted" />
                  <Bar dataKey="Upper" fill="#1E3A5F" name="Upper Bound" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Stats Sidebar */}
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <p className="text-sm text-gray-500">Trend</p>
              <p className={`text-xl font-bold mt-1 ${
                forecast.trend_direction === 'increasing' ? 'text-green-400' : 
                forecast.trend_direction === 'decreasing' ? 'text-red-400' : 'text-gray-400'
              }`}>
                {forecast.trend_direction}
                <span className="text-sm font-normal text-gray-500 ml-2">
                  ({(forecast.trend_percentage * 100).toFixed(1)}%)
                </span>
              </p>
            </div>
            
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <p className="text-sm text-gray-500">Avg Daily (History)</p>
              <p className="text-xl font-bold text-white mt-1">
                {(forecast.historical_avg_daily || 0).toFixed(1)} units
              </p>
            </div>
            
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <p className="text-sm text-gray-500">Avg Daily (Predicted)</p>
              <p className="text-xl font-bold text-blue-400 mt-1">
                {(forecast.predicted_avg_daily || 0).toFixed(1)} units
              </p>
            </div>
            
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <p className="text-sm text-gray-500">Total Volume</p>
              <p className="text-xl font-bold text-white mt-1">
                {Math.round(forecast.predicted_total || 0).toLocaleString()} units
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}