import React from 'react';
import { getDownloadUrl } from '../api';
import type { JobInfo } from '../api';


interface PreviewPanelProps {
  job: JobInfo | null;
}

export const PreviewPanel: React.FC<PreviewPanelProps> = ({ job }) => {
  if (!job || job.status !== 'done') {
    return null;
  }

  const videoUrl = getDownloadUrl(job.job_id, 'final');

  return (
    <div className="card preview-panel fade-in">
      <h2>🖥️ Video Player Preview</h2>
      <div className="video-player-wrapper">
        <video 
          key={job.job_id}
          controls 
          className={`preview-video-player ${job.output_format.includes('9_16') ? 'aspect-9-16' : ''}`}
        >
          <source src={videoUrl} type="video/mp4" />
          Your browser does not support the video tag.
        </video>
      </div>
      <div className="preview-footer">
        <span className="info-badge">Output: {job.output_format.replace(/_/g, ' ').toUpperCase()}</span>
        <span className="info-badge">Voice: {job.tts_voice.split('-').pop()}</span>
      </div>
    </div>
  );
};
