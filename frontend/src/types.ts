export type Status = 'queued' | 'running' | 'completed' | 'failed'
export type Sentence = { id: string; start: number; end: number; text: string }
export type Shot = Sentence & { description: string; role: string; rhythm: string; uncertain: boolean; thumbnail: string | null }
export type Overview = { topic: string; audience: string; hook: string; structure: string; rhythm: string; observations: string; takeaways: string; uncertainties: string }
export type Analysis = {
  id: string; title: string; source_url: string; source_type: string; status: Status; stage: string;
  progress: number; message: string; error: { code: string; message: string } | null;
  created_at: string; updated_at: string; duration: number; width: number; height: number;
  video_url: string | null; cover_url: string | null; warnings: string[];
  transcript: Sentence[]; shots: Shot[]; overview: Overview | null;
}
export type HistoryItem = Omit<Analysis, 'transcript' | 'shots' | 'overview'>
export type Health = { configured: boolean; missing: string[]; media_available: boolean; vision_model: string; asr_model: string; active_id: string | null }
