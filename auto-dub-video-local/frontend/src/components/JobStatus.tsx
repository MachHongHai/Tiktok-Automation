import React, { useEffect, useRef } from 'react';
import { getDownloadUrl } from '../api';
import type { JobInfo } from '../api';


interface JobStatusProps {
  job: JobInfo | null;
  logs: string;
  onProcess: () => void;
  onStop: () => void;
  isProcessing: boolean;
  isStopping: boolean;
}

const STEP_LABELS: Record<string, string> = {
  pending: 'Chờ bắt đầu (Pending)',
  starting: 'Đang khởi động pipeline...',
  scheduled: 'Đã lên lịch chạy...',
  extracting_audio: 'Đang trích xuất âm thanh từ video (Extracting audio)...',
  transcribing: 'Đang nhận diện giọng nói (Speech-to-text)...',
  translating: 'Đang dịch thuật phụ đề (Translating to Vietnamese)...',
  creating_subtitle: 'Đang tạo tệp phụ đề SRT (Creating subtitle)...',
  creating_voice: 'Đang tạo lồng tiếng bằng AI (Text-to-speech)...',
  building_audio_timeline: 'Đang trộn ghép giọng đọc vào timeline (Mixing audio)...',
  rendering: 'Đang biên tập và xuất video final (Rendering)...',
  done: 'Hoàn thành (Done)',
  failed: 'Thất bại (Failed)',
};

export const JobStatus: React.FC<JobStatusProps> = ({
  job,
  logs,
  onProcess,
  onStop,
  isProcessing,
  isStopping,
}) => {
  const terminalRef = useRef<HTMLPreElement>(null);

  // Auto-scroll logs terminal to bottom
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  if (!job) {
    return (
      <div className="card status-panel empty">
        <h2>3. Job Execution & Status</h2>
        <div className="empty-state">
          <span className="icon">⚙️</span>
          <p>Please upload a video and click Process to launch the pipeline.</p>
        </div>
      </div>
    );
  }

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'done': return 'status-done';
      case 'failed': return 'status-failed';
      case 'processing': return 'status-running';
      default: return 'status-pending';
    }
  };

  const getStepLabel = (step: string) => {
    return STEP_LABELS[step] || step || 'Đang xử lý...';
  };

  return (
    <div className="card status-panel">
      <div className="status-header">
        <h2>3. Execution & Outputs</h2>
        <span className={`badge ${getStatusClass(job.status)}`}>
          {job.status.toUpperCase()}
        </span>
      </div>

      <div className="job-meta">
        <p><strong>Job ID:</strong> {job.job_id}</p>
        <p><strong>Original File:</strong> {job.original_filename}</p>
        <p><strong>Mode:</strong> Mode {job.mode}</p>
      </div>

      {/* Progress Section */}
      <div className="progress-section">
        <div className="progress-info">
          <span className="step-text">{getStepLabel(job.step)}</span>
          <span className="percent-text">{job.progress}%</span>
        </div>
        <div className="progress-bar-container">
          <div 
            className={`progress-bar-fill ${job.status === 'processing' ? 'pulsing' : ''}`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
      </div>

      {/* Trigger Processing Button */}
      {job.status === 'pending' && (
        <button 
          className="btn btn-primary btn-process"
          onClick={onProcess}
          disabled={isProcessing}
        >
          {isProcessing ? 'Starting...' : '🚀 Start Pipeline Process'}
        </button>
      )}

      {/* Stop Processing Button */}
      {job.status === 'processing' && (
        <button 
          className="btn btn-danger"
          onClick={onStop}
          disabled={isStopping}
          style={{ marginBottom: '1rem', width: '100%', padding: '0.75rem', fontWeight: 'bold' }}
        >
          {isStopping ? 'Stopping...' : '🛑 Stop Pipeline Process'}
        </button>
      )}

      {/* Error Details */}
      {job.status === 'failed' && job.error && (
        <div className="error-box">
          <strong>Pipeline Error Details:</strong>
          <p>{job.error}</p>
        </div>
      )}

      {/* Logs Terminal */}
      <div className="logs-container">
        <div className="logs-header">
          <span>Execution logs.txt</span>
          {job.status === 'processing' && <span className="spinner">⏳</span>}
        </div>
        <pre className="logs-terminal" ref={terminalRef}>
          {logs || 'Waiting for pipeline to start...'}
        </pre>
      </div>

      {/* Download Actions */}
      {job.status === 'done' && (
        <div className="download-section fade-in">
          <h3>📦 Generated Outputs</h3>
          <div className="download-grid">
            <a 
              href={getDownloadUrl(job.job_id, 'final')} 
              download 
              className="btn-download final"
            >
              <span className="icon">🎬</span>
              <div className="download-text">
                <span className="title">Final Video</span>
                <span className="subtitle">final.mp4</span>
              </div>
            </a>

            <a 
              href={getDownloadUrl(job.job_id, 'subtitle')} 
              download 
              className="btn-download"
            >
              <span className="icon">📄</span>
              <div className="download-text">
                <span className="title">Subtitles (SRT)</span>
                <span className="subtitle">vi.srt</span>
              </div>
            </a>

            <a 
              href={getDownloadUrl(job.job_id, 'voice')} 
              download 
              className="btn-download"
            >
              <span className="icon">🎵</span>
              <div className="download-text">
                <span className="title">Voiceover Track</span>
                <span className="subtitle">voice_final.wav</span>
              </div>
            </a>

            <a 
              href={getDownloadUrl(job.job_id, 'transcript')} 
              download 
              className="btn-download"
            >
              <span className="icon">⚙️</span>
              <div className="download-text">
                <span className="title">Transcript JSON</span>
                <span className="subtitle">transcript.json</span>
              </div>
            </a>
          </div>
        </div>
      )}
    </div>
  );
};
