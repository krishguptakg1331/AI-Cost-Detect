import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Play, AlertCircle, MapPin, Users } from 'lucide-react';
import ProgressTracker from '../components/ProgressTracker';

const API_BASE_URL = 'http://localhost:8000';

interface OrgUser {
  id: string;
  email: string;
  latest_region: string | null;
}

export default function Dashboard() {
  const [regions, setRegions] = useState<string[]>([]);
  const [selectedRegion, setSelectedRegion] = useState('');
  
  const [orgUsers, setOrgUsers] = useState<OrgUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<string>('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('token');
        const headers = { Authorization: `Bearer ${token}` };

        // Fetch Regions
        const resRegions = await axios.get(`${API_BASE_URL}/api/regions`, { headers });
        const regionData = resRegions.data.regions || [];
        const regionStrings = regionData.map((r: any) => typeof r === 'string' ? r : r.region_name);
        setRegions(regionStrings);
        if (regionStrings.length > 0) {
          setSelectedRegion(regionStrings[0]);
        }

        // Fetch Org Users
        try {
          const resUsers = await axios.get(`${API_BASE_URL}/api/org-users`, { headers });
          const users = resUsers.data.users || [];
          setOrgUsers(users);
          
          let defaultUser = users.length > 0 ? users[0] : null;
          
          const currentUserStr = localStorage.getItem('user');
          if (currentUserStr) {
            const currentUser = JSON.parse(currentUserStr);
            const found = users.find((u: OrgUser) => u.id === currentUser.id);
            if (found) defaultUser = found;
          }
          
          if (defaultUser) {
            setSelectedUser(defaultUser.id);
            if (defaultUser.latest_region && regionStrings.includes(defaultUser.latest_region)) {
              setSelectedRegion(defaultUser.latest_region);
            } else if (regionStrings.includes('us-east-1')) {
              setSelectedRegion('us-east-1');
            }
          } else if (regionStrings.includes('us-east-1')) {
             setSelectedRegion('us-east-1');
          }
        } catch (err) {
          console.warn("Could not fetch org users", err);
          if (regionStrings.includes('us-east-1')) {
            setSelectedRegion('us-east-1');
          }
        }

      } catch (err: any) {
        setError(err.response?.data?.detail?.message || 'Failed to fetch data');
      }
    };
    fetchData();
  }, []);

  const handleUserChange = (newUserId: string) => {
    setSelectedUser(newUserId);
    const user = orgUsers.find(u => u.id === newUserId);
    if (user && user.latest_region && regions.includes(user.latest_region)) {
      setSelectedRegion(user.latest_region);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedRegion) return;
    
    setError('');
    setLoading(true);
    // Generate a temporary ID for websocket tracking (backend will return the real one)
    const tempId = crypto.randomUUID();
    setAnalysisId(tempId);

    try {
      const token = localStorage.getItem('token');
      
      const res = await axios.post(
        `${API_BASE_URL}/api/analyze`,
        { region: selectedRegion, user_id: selectedUser },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      // The backend has completed the analysis and returned the result
      navigate(`/report/${res.data.analysis_id || tempId}`, { state: { result: res.data } });
    } catch (err: any) {
      setError(err.response?.data?.detail?.message || 'Analysis failed');
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto mt-10">
      <div className="glass-panel rounded-2xl p-8 relative overflow-hidden">
        {/* Glow effect behind the dashboard */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob"></div>
        <div className="absolute -bottom-8 -left-8 w-64 h-64 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>

        <div className="relative z-10">
          <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white to-gray-400 mb-2">New Analysis</h1>
          <p className="text-gray-300 mb-8 font-medium">Select an organization user and AWS Region to scan for cost optimization opportunities.</p>

          {error && (
            <div className="bg-red-500/10 border border-red-500/50 text-red-400 px-4 py-3 rounded-lg mb-6 flex items-start space-x-3 backdrop-blur-md">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div className="glass-card rounded-xl p-6">
              <label className="block text-sm font-semibold text-gray-200 mb-3">
                Target User (Organization)
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Users className="h-5 w-5 text-indigo-400" />
                </div>
                <select
                  value={selectedUser}
                  onChange={(e) => handleUserChange(e.target.value)}
                  disabled={loading}
                  className="glass-input block w-full pl-12 p-3 appearance-none rounded-lg font-medium"
                >
                  {orgUsers.length === 0 ? (
                    <option value="" className="text-black">Loading users...</option>
                  ) : (
                    orgUsers.map((u) => (
                      <option key={u.id} value={u.id} className="text-black">
                        {u.email}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>

            <div className="glass-card rounded-xl p-6">
              <label className="block text-sm font-semibold text-gray-200 mb-3">
                Target AWS Region
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <MapPin className="h-5 w-5 text-purple-400" />
                </div>
                <select
                  value={selectedRegion}
                  onChange={(e) => setSelectedRegion(e.target.value)}
                  disabled={loading}
                  className="glass-input block w-full pl-12 p-3 appearance-none rounded-lg font-medium"
                >
                  {regions.length === 0 ? (
                    <option value="" className="text-black">Loading regions...</option>
                  ) : (
                    regions.map((region) => (
                      <option key={region} value={region} className="text-black">
                        {region}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <button
              onClick={handleAnalyze}
              disabled={loading || !selectedRegion || !selectedUser}
              className="glass-button flex items-center justify-center space-x-2 px-8 py-3.5 rounded-xl font-bold text-lg w-full md:w-auto disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
            >
              <Play className="w-6 h-6 fill-current" />
              <span>{loading ? 'Analyzing...' : 'Run Analysis'}</span>
            </button>
          </div>

          {loading && analysisId && (
            <div className="mt-8">
              <ProgressTracker 
                analysisId={analysisId} 
                onComplete={() => {}} 
                onError={(msg) => setError(msg)} 
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
