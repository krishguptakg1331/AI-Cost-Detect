import { useEffect, useState, useRef } from 'react';
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';

interface ProgressTrackerProps {
  analysisId: string | null;
  onComplete: (data: any) => void;
  onError: (error: string) => void;
}

interface Step {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  message: string;
}

const INITIAL_STEPS: Step[] = [
  { id: 'scanning', label: 'Scan AWS Resources', status: 'pending', message: 'Waiting to start...' },
  { id: 'detecting', label: 'Run Rule-Based Detection', status: 'pending', message: 'Waiting...' },
  { id: 'analyzing', label: 'AI Cost Analysis', status: 'pending', message: 'Waiting...' },
  { id: 'saving', label: 'Save Results', status: 'pending', message: 'Waiting...' },
];

export default function ProgressTracker({ analysisId, onComplete, onError }: ProgressTrackerProps) {
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!analysisId) return;

    // Reset steps when a new analysis starts
    setSteps(INITIAL_STEPS);

    // Connect WebSocket
    const ws = new WebSocket(`ws://localhost:8000/ws/progress/${analysisId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('WS Message:', data);

        if (data.step === 'error') {
          onError(data.message);
          setSteps(current => current.map(s => 
            s.status === 'running' ? { ...s, status: 'error', message: data.message } : s
          ));
          ws.close();
          return;
        }

        setSteps(current => {
          return current.map(step => {
            if (step.id === data.step) {
              return { ...step, status: data.progress === 100 ? 'completed' : 'running', message: data.message };
            }
            // Mark previous steps as completed
            const stepIndex = current.findIndex(s => s.id === step.id);
            const currentStepIndex = current.findIndex(s => s.id === data.step);
            if (stepIndex < currentStepIndex && step.status !== 'completed') {
              return { ...step, status: 'completed' };
            }
            return step;
          });
        });

        if (data.step === 'complete' || data.progress === 100) {
          // Analysis is fully complete, parent component should handle fetching the result or it might have already received it via HTTP
        }
      } catch (err) {
        console.error('Error parsing WS message', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    return () => {
      try {
        ws.close();
      } catch (e) {
        // Ignore errors on close
      }
    };
  }, [analysisId, onError]);

  if (!analysisId) return null;

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mt-8">
      <h3 className="text-lg font-semibold text-white mb-6">Analysis Progress</h3>
      <div className="space-y-6">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-start">
            <div className="flex flex-col items-center mr-4">
              <div className={`flex items-center justify-center w-8 h-8 rounded-full border-2 
                ${step.status === 'completed' ? 'bg-green-500/20 border-green-500 text-green-500' : ''}
                ${step.status === 'running' ? 'bg-blue-500/20 border-blue-500 text-blue-500' : ''}
                ${step.status === 'error' ? 'bg-red-500/20 border-red-500 text-red-500' : ''}
                ${step.status === 'pending' ? 'border-gray-600 text-gray-500' : ''}
              `}>
                {step.status === 'completed' && <CheckCircle2 className="w-5 h-5" />}
                {step.status === 'running' && <Loader2 className="w-5 h-5 animate-spin" />}
                {step.status === 'error' && <AlertCircle className="w-5 h-5" />}
                {step.status === 'pending' && <Circle className="w-5 h-5" />}
              </div>
              {index < steps.length - 1 && (
                <div className={`w-0.5 h-full my-2 ${
                  steps[index + 1].status !== 'pending' ? 'bg-blue-500' : 'bg-gray-700'
                }`} />
              )}
            </div>
            <div className="pt-1">
              <p className={`font-medium ${
                step.status === 'completed' ? 'text-green-400' : 
                step.status === 'running' ? 'text-blue-400' : 
                step.status === 'error' ? 'text-red-400' : 'text-gray-400'
              }`}>
                {step.label}
              </p>
              <p className="text-sm text-gray-400 mt-1">{step.message}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
