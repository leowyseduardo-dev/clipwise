export type JobStatus = "queued" | "processing" | "ready" | "failed" | "cancelled";

export type LayoutMode =
  | "auto"
  | "vertical"
  | "split"
  | "centrado"
  | "horizontal"
  | "dividido"
  | "trio"
  | "cuarteto"
  | "cam_juego"
  | "dos_cams_juego"
  | "tres_cams_juego"
  | "trio_juego"
  | "spotlight";

export type TitleCardStyle = "impact" | "clean" | "box";
export type TitleCardPosition = "top" | "center" | "bottom";

export type LiveSessionStatus =
  | "connecting"
  | "recording"
  | "stopped"
  | "offline"
  | "error";

export interface LiveClip {
  id: string;
  session_id: string;
  title: string;
  platform: string;
  author: string;
  seconds: number;
  created_at: string | null;
  file: string | null;
}

export interface LiveSession {
  id: string;
  url: string;
  platform: string;
  title: string;
  author: string;
  status: LiveSessionStatus;
  error: string | null;
  started_at: string | null;
  buffer_seconds: number;
  buffer_minutes: number;
  clips: LiveClip[];
}

export interface JobOptions {
  max_clips?: number | null;
  subtitle_style?: string;
  remove_silences?: boolean;
  dynamic_zoom?: boolean;
  language?: string | null;
  layout?: LayoutMode;
  context_overlay?: boolean;
  title_card?: string;
  title_card_seconds?: number;
  title_card_position?: TitleCardPosition;
  title_card_style?: TitleCardStyle;
}

export type ClipCategory =
  | "angry"
  | "funny"
  | "crazy_reactions"
  | "epic"
  | "unexpected"
  | "scary"
  | "fails"
  | "wins"
  | "drama"
  | "shocking";

export interface ScoreBreakdown {
  hook?: number;
  clarity?: number;
  interest?: number;
  pacing?: number;
  retention?: number;
  intensity?: number;
  surprise?: number;
  humor?: number;
  originality?: number;
  importance?: number;
  conversation?: number;
  entertainment?: number;
  context?: number;
  category_confidence?: number;
  total?: number;
}

export interface SubtitleWord {
  w: string;
  start: number;
  end: number;
  p?: number;
}

export interface SubtitleCue {
  start: number;
  end: number;
  text: string;
  words?: SubtitleWord[];
}

export interface CameraBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ClipOverlay {
  voices?: {start:number;end:number;voice:number}[];
  render_options?: {
    platform?: string; sound_accent?: boolean; logo_id?: string; transition?: string; aspect?: string; caption_font?: string; caption_color?: string; accent_color?: string;
    music_level?: number | null; saturation?: number; brand_text?: string;
    layout?: LayoutMode;
    remove_silences?: boolean;
    dynamic_zoom?: boolean;
    context_overlay?: boolean;
    title_card?: string;
    title_card_seconds?: number;
    title_card_position?: TitleCardPosition;
    title_card_style?: TitleCardStyle;
    manual_cams?: CameraBox[];
  };
  kicker?: string;
  context?: string;
  streamer?: string;
  game?: string;
  is_gaming?: boolean;
  context_seconds?: number;
}

export type PublishPlatform = "youtube" | "tiktok";

export type AIProvider = "heuristic" | "openrouter" | "gemini" | "ollama" | "custom";
export type AISettings = {
  provider: AIProvider;
  model: string;
  base_url: string;
  key_set: boolean;
  enabled: boolean;
  last_error: string;
  retry_after: number;
  providers: { id: AIProvider; label: string; model: string; base_url: string; key_url: string; note: string }[];
};

export type PublishRecordStatus =
  | "queued"
  | "uploading"
  | "processing"
  | "published"
  | "failed";

export interface PublishingSettings {
  youtube_client_id: string;
  youtube_client_secret_set: boolean;
  tiktok_client_key: string;
  tiktok_client_secret_set: boolean;
  redirect_host: string;
  redirect_port: number;
  redirect_uri: string;
  youtube_privacy: "private" | "unlisted" | "public" | string;
  tiktok_privacy:
    | "PUBLIC_TO_EVERYONE"
    | "MUTUAL_FOLLOW_FRIENDS"
    | "FOLLOWER_OF_CREATOR"
    | "SELF_ONLY"
    | string;
  youtube_configured: boolean;
  tiktok_configured: boolean;
}

export interface PublishingSettingsInput {
  youtube_client_id?: string;
  youtube_client_secret?: string;
  tiktok_client_key?: string;
  tiktok_client_secret?: string;
  redirect_port?: number;
  youtube_privacy?: string;
  tiktok_privacy?: string;
}

export interface PublishingAccount {
  platform: PublishPlatform;
  connected: boolean;
  account_id: string | null;
  account_name: string | null;
  scope: string | null;
  expires_at: string | null;
  metadata: Record<string, unknown>;
}

export interface PublishingConnections {
  youtube: PublishingAccount | null;
  tiktok: PublishingAccount | null;
}

export interface PublishRecord {
  id: string;
  clip_id: string;
  platform: PublishPlatform;
  status: PublishRecordStatus | string;
  progress: number;
  remote_id: string | null;
  remote_url: string | null;
  error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface OAuthStart {
  platform: PublishPlatform;
  state: string;
  auth_url: string;
  redirect_uri: string;
  browser_opened: boolean;
}

export interface OAuthStatus {
  platform: PublishPlatform;
  state: string;
  status: "pending" | "exchanging" | "success" | "error" | string;
  message: string;
  connected: boolean;
  account: PublishingAccount | null;
}

export interface Clip {
  id: string;
  idx: number;
  start: number;
  end: number;
  duration: number | null;
  score: number | null;
  score_breakdown: ScoreBreakdown;
  category?: ClipCategory | string | null;
  title: string | null;
  hook: string | null;
  reason: string | null;
  caption: string | null;
  description: string | null;
  tags: string[];
  style: string;
  status: string;
  error: string | null;
  subtitles: { cues: SubtitleCue[] };
  overlay?: ClipOverlay;
  video_url: string | null;
  thumb_url: string | null;
  updated_at: string;
}

export interface Job {
  archived?: boolean;
  id: string;
  created_at: string;
  updated_at: string;
  source_type: "youtube" | "kick" | "twitch" | "upload";
  source_url: string | null;
  title: string;
  status: JobStatus;
  stage: string;
  progress: number;
  error: string | null;
  duration: number | null;
  language: string | null;
  clips_target: number;
  options: JobOptions;
  has_music: boolean;
  meta?: Record<string, unknown>;
  streamer?: string;
  game?: string;
  is_gaming?: boolean;
  long_mode?: boolean;
  clips?: Clip[];
}

export interface Health {
  status: string;
  version: string;
  ffmpeg: { available: boolean; version: string | null; path?: string };
  ffprobe: { available: boolean; version: string | null; path?: string };
  whisper_model: string;
  llm: "enabled" | "heuristic" | string;
  subtitle_styles: string[];
  default_style: string;
  max_clips: number;
  max_upload_mb: number;
  max_source_minutes: number;
  long_source_minutes?: number;
  layout_modes?: string[];
  context_overlay?: boolean;
}

export interface SubtitleStyleOption {
  id: string;
  name: string;
  description: string;
}

export interface LayoutOption {
  id: LayoutMode | string;
  name: string;
  description: string;
}

export interface OptionsResponse {
  subtitle_styles: SubtitleStyleOption[];
  default_style: string;
  min_clips: number;
  max_clips: number;
  layouts?: LayoutOption[];
  title_card_styles?: { id: TitleCardStyle | string; name: string }[];
  title_card_positions?: { id: TitleCardPosition | string; name: string }[];
  context_overlay?: boolean;
  long_source_minutes?: number;
}
