import React from 'react';
import type { JobConfig } from '../api';

interface SettingsPanelProps {
  config: JobConfig;
  setConfig: React.Dispatch<React.SetStateAction<JobConfig>>;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ config, setConfig }) => {
  const handleChange = (key: string, value: any) => {
    setConfig((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleStyleChange = (key: string, value: number) => {
    setConfig((prev) => ({
      ...prev,
      subtitle_style: {
        ...prev.subtitle_style,
        [key]: value,
      },
    }));
  };

  return (
    <div className="card settings-panel">
      <h2>2. Pipeline Settings</h2>

      {/* Mode Selection */}
      <div className="form-group">
        <label>Processing Mode</label>
        <select 
          value={config.mode} 
          onChange={(e) => handleChange('mode', e.target.value)}
        >
          <option value="A">Mode A: Full Auto (Video → Transcribe → Translate → TTS)</option>
          <option value="B">Mode B: Use Vietnamese Subtitle (Video + vi.srt → TTS)</option>
          <option value="C">Mode C: Use Vietnamese Script (Video + script_vi.txt → TTS → Subtitles)</option>
        </select>
        <span className="help-text">
          {config.mode === 'A' && 'Analyzes audio in video, transcribes, translates, synthesizes new voiceover and subtitles.'}
          {config.mode === 'B' && 'Uses the provided SRT subtitle to synthesize voiceover and line timings directly.'}
          {config.mode === 'C' && 'Speaks your script, uses AI to timecode the audio, and overlays the voiceover.'}
        </span>
      </div>

      {/* Source Language (Only visible for Mode A) */}
      {config.mode === 'A' && (
        <div className="form-group fade-in">
          <label>Source Language</label>
          <select 
            value={config.source_language} 
            onChange={(e) => handleChange('source_language', e.target.value)}
          >
            <option value="auto">Automatic Detection</option>
            <option value="en">English (en)</option>
            <option value="zh">Chinese (zh)</option>
          </select>
        </div>
      )}

      {/* TTS Voice */}
      <div className="form-group">
        <label>Vietnamese TTS Voice</label>
        <select 
          value={config.tts_voice} 
          onChange={(e) => handleChange('tts_voice', e.target.value)}
        >
          <option value="vi-VN-HoaiMyNeural">Hoài Mỹ (Female - vi-VN-HoaiMyNeural)</option>
          <option value="vi-VN-NamMinhNeural">Nam Minh (Male - vi-VN-NamMinhNeural)</option>
        </select>
      </div>

      {/* Output Format */}
      <div className="form-group">
        <label>Output Video Layout</label>
        <select 
          value={config.output_format} 
          onChange={(e) => handleChange('output_format', e.target.value)}
        >
          <option value="keep_ratio">Original Aspect Ratio</option>
          <option value="tiktok_9_16_crop">TikTok 9:16 (Center Crop 1080x1920)</option>
          <option value="blur_background_9_16">TikTok 9:16 (Blurred Sides Background)</option>
        </select>
      </div>

      {/* Original Video Volume */}
      <div className="form-group">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <label>Original Video Volume (Background Music)</label>
          <span style={{ fontWeight: 'bold', color: '#4f46e5' }}>{config.original_video_volume}%</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <input 
            type="range" 
            min="0" 
            max="100" 
            step="5"
            value={config.original_video_volume}
            onChange={(e) => handleChange('original_video_volume', parseInt(e.target.value) || 0)}
            style={{ flex: 1, cursor: 'pointer' }}
          />
        </div>
        <span className="help-text">
          {config.original_video_volume === 0 
            ? 'Mutes original video background music completely.' 
            : `Original video background music volume set to ${config.original_video_volume}% (reduced by ~${Math.abs(Math.round(20 * Math.log10(config.original_video_volume / 100)))} dB).`}
        </span>
      </div>



      {/* Subtitles Style */}
      <fieldset className="subtitle-styling">
        <legend>Subtitle Style Settings</legend>
        
        <div className="grid-2-col">
          <div className="form-group">
            <label>Font Size (px)</label>
            <input 
              type="number" 
              min="10" 
              max="100" 
              value={config.subtitle_style.font_size}
              onChange={(e) => handleStyleChange('font_size', parseInt(e.target.value) || 14)}
            />
          </div>
          
          <div className="form-group">
            <label>Outline Width (px)</label>
            <input 
              type="number" 
              min="0" 
              max="10" 
              value={config.subtitle_style.outline}
              onChange={(e) => handleStyleChange('outline', parseInt(e.target.value) || 0)}
            />
          </div>
        </div>

        <div className="grid-2-col">
          <div className="form-group">
            <label>Margin Bottom (px)</label>
            <input 
              type="number" 
              min="10" 
              max="300" 
              value={config.subtitle_style.margin_bottom}
              onChange={(e) => handleStyleChange('margin_bottom', parseInt(e.target.value) || 40)}
            />
          </div>
          
          <div className="form-group">
            <label>Max Chars / Line</label>
            <input 
              type="number" 
              min="10" 
              max="100" 
              value={config.subtitle_style.max_chars_per_line}
              onChange={(e) => handleStyleChange('max_chars_per_line', parseInt(e.target.value) || 32)}
            />
          </div>
        </div>
      </fieldset>
    </div>
  );
};
