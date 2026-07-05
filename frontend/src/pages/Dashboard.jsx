import { useEffect, useState } from 'react';
import { Package, AlertTriangle, DollarSign, TrendingUp } from 'lucide-react';
import StatCard from '../components/StatCard';
import { getInventorySummary, getLowStockAlerts } from '../api/services';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [sumRes, alertRes] = await Promise.all([
          getInventorySummary(),
          getLowStockAlerts(),
        ]);
        setSummary(sumRes.data);
        setAlerts(alertRes.data.items || []);
      } catch (err) {
        console.error("Failed to fetch dashboard data", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Loading dashboard...</div>;
  if (!summary) return <div className="p-8 text-red-500">Failed to load data. Is the backend running?</div>;

  return (
    <div className="p-8 space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white">Inventory Dashboard</h2>
        <p className="text-gray-500 mt-1">Real-time overview of your retail operations</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Total Products" value={summary.total_products} icon={Package} color="blue" />
        <StatCard title="Out of Stock" value={summary.out_of_stock} icon={AlertTriangle} color="red" />
        <StatCard title="Low Stock" value={summary.low_stock} icon={TrendingUp} color="yellow" />
        <StatCard title="Inventory Value" value={`$${summary.total_inventory_value?.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`} icon={DollarSign} color="green" />
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Critical Stock Alerts</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase text-gray-500 border-b border-gray-800">
              <tr>
                <th className="pb-3 font-medium">Product</th>
                <th className="pb-3 font-medium">SKU</th>
                <th className="pb-3 font-medium">Store</th>
                <th className="pb-3 font-medium">Current Stock</th>
                <th className="pb-3 font-medium">Reorder Point</th>
                <th className="pb-3 font-medium">Deficit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {alerts.slice(0, 5).map((item, i) => (
                <tr key={i} className="text-gray-300">
                  <td className="py-3 font-medium text-white">{item.name}</td>
                  <td className="py-3 text-gray-400">{item.sku}</td>
                  <td className="py-3 text-gray-400">{item.store_id}</td>
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded text-xs font-bold ${item.quantity_on_hand === 0 ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                      {item.quantity_on_hand}
                    </span>
                  </td>
                  <td className="py-3">{item.reorder_point}</td>
                  <td className="py-3 text-red-400 font-medium">{item.deficit}</td>
                </tr>
              ))}
              {alerts.length === 0 && <tr><td colSpan="6" className="py-4 text-center text-gray-500">No critical alerts!</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}