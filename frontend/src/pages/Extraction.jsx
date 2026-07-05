import { useState } from 'react';
import { FileText } from 'lucide-react';
import { extractFromReport } from '../api/services';

export default function Extraction() {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleExtract = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    try {
      const res = await extractFromReport(text);
      setResult(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Unstructured Report Extraction</h2>
        <p className="text-gray-500 mt-1">Paste emails, notes, or PDF text to extract structured retail data</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input */}
        <form onSubmit={handleExtract} className="flex flex-col gap-4 h-full">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`Example:\n"Urgent update: Warehouse-1 is out of Wireless Earbuds Pro. We sold 450 units this week bringing in $35,995 in revenue. Denim Jeans at store-nyc-01 are critically low at 15 units."`}
            className="flex-1 min-h-[400px] bg-gray-900 border border-gray-800 rounded-xl p-4 text-gray-200 outline-none resize-none focus:border-blue-500 placeholder-gray-600"
          />
          <button 
            type="submit" 
            disabled={loading || !text.trim()}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? 'Extracting with AI...' : 'Extract Data'}
          </button>
        </form>

        {/* Output */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 overflow-y-auto max-h-[550px]">
          {!result && !loading && (
            <div className="h-full flex flex-col items-center justify-center text-gray-600">
              <FileText size={48} className="mb-4 opacity-50" />
              <p>Extracted data will appear here</p>
            </div>
          )}
          {loading && <div className="text-center text-gray-400 animate-pulse mt-20">Analyzing document...</div>}
          {result && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Summary</h3>
                <p className="text-gray-200">{result.summary}</p>
              </div>
              
              <div className={`inline-block px-3 py-1 rounded-full text-sm font-bold ${
                result.sentiment === 'positive' ? 'bg-green-500/20 text-green-400' : 
                result.sentiment === 'negative' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20 text-gray-400'
              }`}>
                Sentiment: {result.sentiment}
              </div>

              {result.products_mentioned?.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Products Found</h3>
                  <div className="flex flex-wrap gap-2">
                    {result.products_mentioned.map((p, i) => (
                      <span key={i} className="bg-blue-500/20 text-blue-300 px-3 py-1 rounded-lg text-sm">{p}</span>
                    ))}
                  </div>
                </div>
              )}

              {result.key_metrics && Object.keys(result.key_metrics).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Key Metrics</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(result.key_metrics).map(([key, val]) => 
                      val !== null && val !== undefined ? (
                        <div key={key} className="bg-gray-800 rounded-lg p-3">
                          <p className="text-xs text-gray-500">{key.replace(/_/g, ' ')}</p>
                          <p className="text-lg font-bold text-white">{typeof val === 'number' ? val.toLocaleString() : val}</p>
                        </div>
                      ) : null
                    )}
                  </div>
                </div>
              )}

              {result.action_items?.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">Action Items</h3>
                  <ul className="space-y-2">
                    {result.action_items.map((item, i) => (
                      <li key={i} className="flex items-start gap-2 text-gray-300">
                        <span className="text-yellow-500 mt-1">•</span> {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}