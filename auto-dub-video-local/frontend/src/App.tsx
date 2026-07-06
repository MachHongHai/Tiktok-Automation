import { useState, useEffect, useRef } from 'react';
import { 
  createJob, 
  listJobs, 
  getJobStatus, 
  getJobLogs, 
  processJob,
  deleteJob,
  stopJob
} from './api';
import type { JobInfo, JobConfig } from './api';

import { UploadPanel } from './components/UploadPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { JobStatus } from './components/JobStatus';
import { PreviewPanel } from './components/PreviewPanel';

const DEFAULT_CONFIG: JobConfig = {
  mode: 'A',
  source_language: 'auto',
  target_language: 'vi',
  tts_voice: 'vi-VN-HoaiMyNeural',
  subtitle_style: {
    font_size: 14,
    margin_bottom: 40,
    outline: 2,
    max_chars_per_line: 32,
  },
  output_format: 'keep_ratio',
  enable_audio_separation: true,
  original_video_volume: 60,
};

export default function App() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [srtFile, setSrtFile] = useState<File | null>(null);
  const [scriptFile, setScriptFile] = useState<File | null>(null);
  const [config, setConfig] = useState<JobConfig>(DEFAULT_CONFIG);
  
  const [activeJob, setActiveJob] = useState<JobInfo | null>(null);
  const [jobsList, setJobsList] = useState<JobInfo[]>([]);
  const [logs, setLogs] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [isStopping, setIsStopping] = useState<boolean>(false);

  const pollingIntervalRef = useRef<number | null>(null);

  // Load history list on startup
  useEffect(() => {
    fetchJobsHistory();
  }, []);

  // Poll active job status when running
  useEffect(() => {
    if (activeJob && (activeJob.status === 'processing' || activeJob.status === 'pending')) {
      startPolling(activeJob.job_id);
    } else {
      stopPolling();
    }
    return () => stopPolling();
  }, [activeJob?.status, activeJob?.job_id]);

  const fetchJobsHistory = async () => {
    try {
      const list = await listJobs();
      setJobsList(list);
    } catch (err: any) {
      console.error('Failed to load history:', err);
    }
  };

  const startPolling = (jobId: string) => {
    stopPolling(); // clear any previous intervals
    
    // Immediate poll once
    pollJob(jobId);
    
    // Set 2-second interval
    pollingIntervalRef.current = window.setInterval(() => {
      pollJob(jobId);
    }, 2000);
  };

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  };

  const pollJob = async (jobId: string) => {
    try {
      const status = await getJobStatus(jobId);
      setActiveJob(status);
      
      const logContent = await getJobLogs(jobId);
      setLogs(logContent);
      
      if (status.status === 'done' || status.status === 'failed') {
        stopPolling();
        fetchJobsHistory();
      }
    } catch (err: any) {
      console.error('Error polling job status:', err);
    }
  };

  const handleCreateJob = async () => {
    if (!videoFile) {
      setError('Please select a video file first.');
      return;
    }
    if (config.mode === 'B' && !srtFile) {
      setError('Please select a Vietnamese SRT subtitle file for Mode B.');
      return;
    }
    if (config.mode === 'C' && !scriptFile) {
      setError('Please select a Vietnamese script TXT file for Mode C.');
      return;
    }

    setError(null);
    setIsUploading(true);
    setLogs('Uploading files to server...');
    
    try {
      // 1. Upload video and register Job
      const job = await createJob(videoFile, config, srtFile || undefined, scriptFile || undefined);
      setActiveJob(job);
      setIsUploading(false);
      fetchJobsHistory();
      
      // 2. Automatically trigger pipeline process
      await handleStartProcess(job.job_id);
    } catch (err: any) {
      setError(err.message || 'Failed to create and upload job');
      setIsUploading(false);
      setLogs((prev) => prev + `\nError: ${err.message}`);
    }
  };

  const handleStartProcess = async (jobId: string) => {
    setIsProcessing(true);
    try {
      const scheduled = await processJob(jobId);
      setActiveJob(scheduled);
      startPolling(jobId);
    } catch (err: any) {
      setError(err.message || 'Failed to schedule job run');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSelectJobFromHistory = async (job: JobInfo) => {
    setError(null);
    setActiveJob(job);
    try {
      const logContent = await getJobLogs(job.job_id);
      setLogs(logContent);
    } catch (err: any) {
      setLogs('Logs not available.');
    }
  };

  const handleDeleteJob = async (jobId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Stop click event propagation to parent div
    
    const targetJob = jobsList.find((j) => j.job_id === jobId);
    if (targetJob && targetJob.status === 'processing') {
      alert('Không thể xóa công việc đang trong quá trình xử lý.');
      return;
    }

    if (!window.confirm('Bạn có chắc chắn muốn xóa video đã xử lý này? Thao tác này sẽ xóa vĩnh viễn tất cả tệp tin liên quan.')) {
      return;
    }

    try {
      await deleteJob(jobId);
      
      // Clear active details if the deleted job was selected
      if (activeJob?.job_id === jobId) {
        setActiveJob(null);
        setLogs('');
      }
      
      await fetchJobsHistory();
    } catch (err: any) {
      alert(`Lỗi khi xóa công việc: ${err.message}`);
    }
  };

  const handleStopProcess = async () => {
    if (!activeJob) return;

    if (!window.confirm('Bạn có chắc chắn muốn dừng quy trình xử lý video này?')) {
      return;
    }

    setIsStopping(true);
    try {
      const updatedJob = await stopJob(activeJob.job_id);
      setActiveJob(updatedJob);
      stopPolling();
      
      // Fetch latest logs to show the cancellation status
      try {
        const logContent = await getJobLogs(activeJob.job_id);
        setLogs(logContent);
      } catch (e) {}

      await fetchJobsHistory();
    } catch (err: any) {
      alert(`Lỗi khi dừng quy trình: ${err.message}`);
    } finally {
      setIsStopping(false);
    }
  };

  return (
    <div className="app-container">
      {/* Sleek Gradient Header */}
      <header className="app-header">
        <div className="header-logo">
          <span className="logo-icon">🔊</span>
          <div>
            <h1>Auto Dub Video Local</h1>
            <p>Automate voice dubbing and subtitle burns in high-fidelity Vietnamese</p>
          </div>
        </div>
        <div className="header-status">
          <span className="dot active"></span>
          <span>Localhost Backend Active</span>
        </div>
      </header>

      {/* Main Dashboard Layout */}
      <main className="dashboard-grid">
        {/* Left Side: Inputs and Settings */}
        <section className="input-column">
          <UploadPanel 
            videoFile={videoFile}
            setVideoFile={setVideoFile}
            srtFile={srtFile}
            setSrtFile={setSrtFile}
            scriptFile={scriptFile}
            setScriptFile={setScriptFile}
            mode={config.mode}
          />
          
          <SettingsPanel 
            config={config}
            setConfig={setConfig}
          />

          {error && <div className="error-banner">⚠️ {error}</div>}

          <button 
            className={`btn btn-large btn-submit ${isUploading ? 'loading' : ''}`}
            onClick={handleCreateJob}
            disabled={isUploading || isProcessing}
          >
            {isUploading ? (
              <>
                <span className="spinner">⏳</span> Uploading Assets...
              </>
            ) : (
              '🚀 Process Video Dub'
            )}
          </button>
        </section>

        {/* Right Side: Progress Status, Logs & Video Preview */}
        <section className="output-column">
          <JobStatus 
            job={activeJob}
            logs={logs}
            onProcess={() => activeJob && handleStartProcess(activeJob.job_id)}
            onStop={handleStopProcess}
            isProcessing={isProcessing}
            isStopping={isStopping}
          />
          
          <PreviewPanel job={activeJob} />
        </section>
      </main>

      {/* Job History Drawer (Bottom Layout) */}
      <footer className="history-section">
        <h2>📂 Recent Jobs ({jobsList.length})</h2>
        {jobsList.length === 0 ? (
          <p className="no-history">No previous runs recorded. Create one above!</p>
        ) : (
          <div className="history-cards-container">
            {jobsList.map((j) => (
              <div 
                key={j.job_id} 
                className={`history-card ${activeJob?.job_id === j.job_id ? 'active' : ''}`}
                onClick={() => handleSelectJobFromHistory(j)}
              >
                <div className="card-top">
                  <span className="mode-badge">Mode {j.mode}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className={`status-dot ${j.status}`} title={`Status: ${j.status}`}></span>
                    <button 
                      className="card-delete-btn" 
                      onClick={(e) => handleDeleteJob(j.job_id, e)}
                      title="Xóa công việc này"
                    >
                      🗑️
                    </button>
                  </div>
                </div>
                <div className="card-filename" title={j.original_filename}>
                  {j.original_filename}
                </div>
                <div className="card-date">
                  {new Date(j.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </footer>
    </div>
  );
}
