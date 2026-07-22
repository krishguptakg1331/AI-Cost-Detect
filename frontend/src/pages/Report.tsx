import { useState, useEffect } from 'react';
import { useParams, useLocation, Link } from 'react-router-dom';
import axios from 'axios';
import { DollarSign, AlertTriangle, Box, ArrowLeft, Terminal, CheckCircle2 } from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

export default function Report() {
  const { id } = useParams();
  const location = useLocation();
  const [data, setData] = useState<any>(location.state?.result || null);
  const [loading, setLoading] = useState(!data);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!data && id) {
      const fetchAnalysis = async () => {
        try {
          const token = localStorage.getItem('token');
          const res = await axios.get(`${API_BASE_URL}/api/analysis/${id}`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          setData(res.data.analysis);
        } catch (err: any) {
          setError(err.response?.data?.detail?.message || 'Failed to fetch analysis report');
        } finally {
          setLoading(false);
        }
      };
      fetchAnalysis();
    }
  }, [id, data]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-red-500/10 border border-red-500/50 text-red-400 p-6 rounded-lg">
          <h3 className="text-lg font-bold mb-2">Error Loading Report</h3>
          <p>{error || 'Report data not found.'}</p>
          <Link to="/history" className="inline-block mt-4 text-red-300 hover:text-white underline">
            Back to History
          </Link>
        </div>
      </div>
    );
  }

  // Handle both direct API response structure and DB structure
  const analysisData = data.analysis_result || data.analysis || {};
  const scanData = data.scan || { total_resources: data.resources_scanned, region: data.region };
  const issues = analysisData.issues || data.detection?.flags || [];
  const totalSavings = analysisData.total_estimated_monthly_savings || data.estimated_savings || 0;
  const summaryText = analysisData.summary || "Analysis completed based on rule-based flags.";

  return (
    <div className="max-w-6xl mx-auto">
      <Link to="/history" className="inline-flex items-center text-gray-400 hover:text-white mb-6 transition-colors">
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to History
      </Link>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 flex items-center space-x-4">
          <div className="p-3 bg-blue-500/10 text-blue-400 rounded-lg">
            <Box className="w-8 h-8" />
          </div>
          <div>
            <p className="text-gray-400 text-sm font-medium">Resources Scanned</p>
            <p className="text-2xl font-bold text-white">{scanData.total_resources}</p>
            <p className="text-xs text-gray-500 mt-1">{scanData.region}</p>
          </div>
        </div>

        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 flex items-center space-x-4">
          <div className="p-3 bg-yellow-500/10 text-yellow-400 rounded-lg">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <div>
            <p className="text-gray-400 text-sm font-medium">Issues Found</p>
            <p className="text-2xl font-bold text-white">{issues.length}</p>
          </div>
        </div>

        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 flex items-center space-x-4">
          <div className="p-3 bg-green-500/10 text-green-400 rounded-lg">
            <DollarSign className="w-8 h-8" />
          </div>
          <div>
            <p className="text-gray-400 text-sm font-medium">Est. Monthly Savings</p>
            <p className="text-2xl font-bold text-white">${Number(totalSavings).toFixed(2)}</p>
          </div>
        </div>
      </div>

      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Executive Summary</h2>
        <p className="text-gray-300 leading-relaxed whitespace-pre-wrap">{summaryText}</p>
      </div>

      <h2 className="text-2xl font-bold text-white mb-6">Actionable Insights</h2>
      
      {issues.length === 0 ? (
        <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-8 text-center">
          <CheckCircle2 className="w-12 h-12 text-green-400 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-white mb-1">Excellent Cloud Hygiene</h3>
          <p className="text-green-200/70">No significant cost-saving opportunities were found in this region.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {issues.map((issue: any, index: number) => (
            <div key={index} className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="p-6 border-b border-gray-700 flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div>
                  <div className="flex items-center space-x-3 mb-2">
                    <span className={`px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider ${
                      issue.severity === 'High' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                      issue.severity === 'Medium' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                      'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                    }`}>
                      {issue.severity || 'Medium'} Priority
                    </span>
                    <span className="px-2.5 py-1 rounded-md bg-gray-700 text-gray-300 text-xs font-medium border border-gray-600">
                      {issue.service || issue.resource_type}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-white">{issue.issue_title || issue.issue_description}</h3>
                  <p className="text-gray-400 mt-2 text-sm max-w-3xl">{issue.explanation || issue.description || 'Issue detected by rule-based scanner.'}</p>
                </div>
                <div className="bg-green-500/10 border border-green-500/20 px-4 py-3 rounded-lg flex flex-col items-center justify-center min-w-[120px]">
                  <span className="text-green-400/80 text-xs font-medium uppercase tracking-wider mb-1">Save</span>
                  <span className="text-xl font-bold text-green-400">
                    ${Number(issue.estimated_monthly_savings || 0).toFixed(2)}
                  </span>
                </div>
              </div>
              
              {issue.resource_id && (
                <div className="px-6 py-3 bg-gray-800/50 border-b border-gray-700 flex items-center space-x-2 text-sm">
                  <span className="text-gray-500">Resource:</span>
                  <span className="font-mono text-gray-300 bg-gray-900 px-2 py-0.5 rounded border border-gray-700">
                    {issue.resource_id}
                  </span>
                </div>
              )}

              {issue.remediation_cli_command && (
                <div className="p-6 bg-gray-900/50">
                  <div className="flex items-center space-x-2 mb-3">
                    <Terminal className="w-4 h-4 text-gray-400" />
                    <h4 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Remediation Command</h4>
                  </div>
                  <div className="relative group">
                    <pre className="bg-black/50 p-4 rounded-lg overflow-x-auto border border-gray-800 text-blue-300 font-mono text-sm">
                      {issue.remediation_cli_command}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
