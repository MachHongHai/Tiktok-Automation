import React, { useRef } from 'react';

interface UploadPanelProps {
  videoFile: File | null;
  setVideoFile: (file: File | null) => void;
  srtFile: File | null;
  setSrtFile: (file: File | null) => void;
  scriptFile: File | null;
  setScriptFile: (file: File | null) => void;
  mode: string;
}

export const UploadPanel: React.FC<UploadPanelProps> = ({
  videoFile,
  setVideoFile,
  srtFile,
  setSrtFile,
  scriptFile,
  setScriptFile,
  mode,
}) => {
  const videoInputRef = useRef<HTMLInputElement>(null);
  const srtInputRef = useRef<HTMLInputElement>(null);
  const scriptInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    setter: (file: File | null) => void
  ) => {
    if (e.target.files && e.target.files.length > 0) {
      setter(e.target.files[0]);
    }
  };

  const triggerSelect = (ref: React.RefObject<HTMLInputElement | null>) => {
    if (ref.current) {
      ref.current.click();
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="card upload-panel">
      <h2>1. Import Media Assets</h2>
      
      {/* Video Selection */}
      <div className="form-group">
        <label>Input Video (.mp4, .mov, .mkv) <span className="required">*</span></label>
        <div 
          className={`dropzone ${videoFile ? 'has-file' : ''}`}
          onClick={() => triggerSelect(videoInputRef)}
        >
          <input 
            type="file" 
            ref={videoInputRef}
            onChange={(e) => handleFileChange(e, setVideoFile)}
            accept=".mp4,.mov,.mkv"
            style={{ display: 'none' }} 
          />
          {videoFile ? (
            <div className="file-info">
              <span className="icon">🎬</span>
              <div className="details">
                <span className="filename">{videoFile.name}</span>
                <span className="filesize">{formatSize(videoFile.size)}</span>
              </div>
            </div>
          ) : (
            <div className="placeholder">
              <span className="icon">📤</span>
              <span className="text">Drag & drop or Click to choose video</span>
            </div>
          )}
        </div>
      </div>

      {/* Conditional Subtitles Upload (Mode B) */}
      {mode === 'B' && (
        <div className="form-group fade-in">
          <label>Vietnamese Subtitles File (.srt) <span className="required">*</span></label>
          <div 
            className={`dropzone secondary ${srtFile ? 'has-file' : ''}`}
            onClick={() => triggerSelect(srtInputRef)}
          >
            <input 
              type="file" 
              ref={srtInputRef}
              onChange={(e) => handleFileChange(e, setSrtFile)}
              accept=".srt"
              style={{ display: 'none' }} 
            />
            {srtFile ? (
              <div className="file-info">
                <span className="icon">📄</span>
                <div className="details">
                  <span className="filename">{srtFile.name}</span>
                  <span className="filesize">{formatSize(srtFile.size)}</span>
                </div>
              </div>
            ) : (
              <div className="placeholder">
                <span className="icon">📝</span>
                <span className="text">Choose Vietnamese subtitle SRT file</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Conditional Script Text Upload (Mode C) */}
      {mode === 'C' && (
        <div className="form-group fade-in">
          <label>Vietnamese Transcript Script (.txt) <span className="required">*</span></label>
          <div 
            className={`dropzone secondary ${scriptFile ? 'has-file' : ''}`}
            onClick={() => triggerSelect(scriptInputRef)}
          >
            <input 
              type="file" 
              ref={scriptInputRef}
              onChange={(e) => handleFileChange(e, setScriptFile)}
              accept=".txt"
              style={{ display: 'none' }} 
            />
            {scriptFile ? (
              <div className="file-info">
                <span className="icon">✍️</span>
                <div className="details">
                  <span className="filename">{scriptFile.name}</span>
                  <span className="filesize">{formatSize(scriptFile.size)}</span>
                </div>
              </div>
            ) : (
              <div className="placeholder">
                <span className="icon">📄</span>
                <span className="text">Choose Vietnamese script TXT file</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
