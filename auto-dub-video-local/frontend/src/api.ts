export interface SubtitleStyle {
  font_size: number;
  margin_bottom: number;
  outline: number;
  max_chars_per_line: number;
}

export interface JobConfig {
  mode: string;
  source_language: string;
  target_language: string;
  tts_voice: string;
  subtitle_style: SubtitleStyle;
  output_format: string;
  enable_audio_separation: boolean;
  original_video_volume: number;
}

export interface JobInfo {
  job_id: string;
  original_filename: string;
  mode: string;
  source_language: string;
  target_language: string;
  tts_voice: string;
  subtitle_style: SubtitleStyle;
  output_format: string;
  enable_audio_separation: boolean;
  original_video_volume: number;
  status: 'pending' | 'processing' | 'done' | 'failed';
  progress: number;
  step: string;
  created_at: string;
  updated_at: string;
  error?: string;
  files: {
    video_input: string;
    srt_input?: string;
    script_input?: string;
    final_video?: string;
    srt_output?: string;
    voice_output?: string;
    transcript_json?: string;
  };
}

const API_BASE = 'http://localhost:8000/api';

export async function createJob(
  videoFile: File,
  config: JobConfig,
  srtFile?: File,
  scriptFile?: File
): Promise<JobInfo> {
  const formData = new FormData();
  formData.append('video', videoFile);
  if (srtFile) formData.append('srt_file', srtFile);
  if (scriptFile) formData.append('script_file', scriptFile);
  
  formData.append('mode', config.mode);
  formData.append('source_language', config.source_language);
  formData.append('target_language', config.target_language);
  formData.append('tts_voice', config.tts_voice);
  formData.append('output_format', config.output_format);
  formData.append('font_size', config.subtitle_style.font_size.toString());
  formData.append('margin_bottom', config.subtitle_style.margin_bottom.toString());
  formData.append('outline', config.subtitle_style.outline.toString());
  formData.append('max_chars_per_line', config.subtitle_style.max_chars_per_line.toString());
  formData.append('enable_audio_separation', config.enable_audio_separation.toString());
  formData.append('original_video_volume', config.original_video_volume.toString());

  const response = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to create job');
  }

  return response.json();
}

export async function listJobs(): Promise<JobInfo[]> {
  const response = await fetch(`${API_BASE}/jobs`);
  if (!response.ok) {
    throw new Error('Failed to fetch jobs list');
  }
  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobInfo> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch job details');
  }
  return response.json();
}

export async function processJob(jobId: string): Promise<JobInfo> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/process`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to start processing');
  }
  return response.json();
}

export async function getJobLogs(jobId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/logs`);
  if (!response.ok) {
    throw new Error('Failed to fetch job logs');
  }
  return response.text();
}

export function getDownloadUrl(jobId: string, type: 'final' | 'subtitle' | 'voice' | 'transcript'): string {
  return `${API_BASE}/jobs/${jobId}/download/${type}`;
}

export async function deleteJob(jobId: string): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to delete job');
  }
  return response.json();
}

export async function stopJob(jobId: string): Promise<JobInfo> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to stop job');
  }
  return response.json();
}



