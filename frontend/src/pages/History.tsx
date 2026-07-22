import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Clock, AlertCircle, ChevronRight, MapPin, DollarSign, AlertTriangle } from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

interface AnalysisHistory {
  id: string;
  region: string;
  created_at: string;
  resources_scanned: number;
  issues_found: number;
  estimated_savings: number;
  status: string;
}

export default function History() {
  const [analyses, setAnalyses] = useState<AnalysisHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await axios.get(`${API_BASE_URL}/api/history`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setAnalyses(res.data.analyses || []);
      } catch (err: any) {
        setError(err.response?.data?.detail?.message || 'Failed to fetch history');
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center space-x-3 mb-8">
        <Clock className="w-8 h-8 text-blue-500" />
        <h1 className="text-3xl font-bold text-white">Analysis History</h1>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg mb-6 flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {analyses.length === 0 && !error ? (
        <div className="bg-gray-800 rounded-xl p-12 text-center border border-gray-700">
          <Clock className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h2 className="text-xl font-medium text-gray-300 mb-2">No analyses yet</h2>
          <p className="text-gray-500 mb-6">Run your first cost analysis to start saving money.</p>
          <Link
            to="/dashboard"
            className="inline-flex items-center px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
          >
            Go to Dashboard
          </Link>
        </div>
      ) : (
        <div className="grid gap-4">
          {analyses.map((analysis) => (
            <Link
              key={analysis.id}
              to={`/report/${analysis.id}`}
              className="bg-gray-800 rounded-xl p-6 border border-gray-700 hover:border-gray-500 hover:bg-gray-800/80 transition-all flex flex-col sm:flex-row sm:items-center justify-between group"
            >
              <div className="flex-1">
                <div className="flex items-center space-x-3 mb-2">
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    analysis.status === 'complete' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                    analysis.status === 'partial' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                    'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}>
                    {analysis.status.toUpperCase()}
                  </span>
                  <span className="text-gray-400 text-sm">
                    {new Date(analysis.created_at).toLocaleDateString(undefined, {
                      year: 'numeric', month: 'short', day: 'numeric',
                      hour: '2-digit', minute: '2-digit'
                    })}
                  </span>
                </div>
                <div className="flex items-center space-x-2 text-xl font-semibold text-white mb-4 sm:mb-0">
                  <MapPin className="w-5 h-5 text-gray-500" />
                  <span>{analysis.region}</span>
                </div>
              </div>

              <div className="flex flex-wrap sm:flex-nowrap gap-4 sm:gap-8 items-center mr-4">
                <div className="flex flex-col">
                  <span className="text-gray-500 text-sm">Resources Scanned</span>
                  <span className="text-gray-200 font-medium">{analysis.resources_scanned}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-gray-500 text-sm">Issues Found</span>
                  <div className="flex items-center space-x-1 text-yellow-400 font-medium">
                    <AlertTriangle className="w-4 h-4" />
                    <span>{analysis.issues_found}</span>
                  </div>
                </div>
                <div className="flex flex-col">
                  <span className="text-gray-500 text-sm">Est. Savings/mo</span>
                  <div className="flex items-center text-green-400 font-medium">
                    <DollarSign className="w-4 h-4" />
                    <span>${analysis.estimated_savings?.toFixed(2) || '0.00'}</span>
                  </div>
                </div>
              </div>

              <div className="hidden sm:flex items-center text-gray-500 group-hover:text-blue-400 transition-colors">
                <ChevronRight className="w-6 h-6" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
