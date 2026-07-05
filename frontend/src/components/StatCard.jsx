export default function StatCard({ title, value, icon: Icon, color = 'blue' }) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-400',
    red: 'bg-red-500/10 text-red-400',
    green: 'bg-green-500/10 text-green-400',
    yellow: 'bg-yellow-500/10 text-yellow-400',
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-center justify-between">
      <div>
        <p className="text-sm text-gray-500 mb-1">{title}</p>
        <p className="text-2xl font-bold text-white">{value}</p>
      </div>
      <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
        {Icon && <Icon size={24} />}
      </div>
    </div>
  );
}