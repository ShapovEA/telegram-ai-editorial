export type User = {
  id: number
  email: string
  name: string
  telegram_linked: boolean
  telegram_username: string | null
}

export type ChannelType = "news" | "smm"
export type ChannelStatus = "draft" | "onboarding" | "active" | "paused"
export type PublishMode = "autopilot" | "approval"
export type PostFormat = "text" | "poll" | "digest"
export type ReasoningLevel = "none" | "minimal" | "low" | "medium" | "high"

export type Role =
  | "account_manager"
  | "designer"
  | "strategist"
  | "scout"
  | "chief"
  | "factchecker"
  | "researcher"
  | "writer"
  | "editor"
  | "publisher"
  | "analyst"
  | "guard"
  | "novelty"

export type Brief = {
  about: string
  audience: string
  goal: string
  voice: string
  avoid: string
  positions: string
  samples: string[]
  site_url: string
}

export type StyleRule = { id: string; text: string; origin: "edits" | "user" }

export type StyleStructured = {
  address: "ty" | "vy"
  length_min: number
  length_max: number
  emoji_max: number
  banned_phrases: string[]
  signature: string
  hashtags: string[]
  links_policy: "source_only" | "none" | "free"
}

export type Styleguide = { structured: StyleStructured; text: string; rules: StyleRule[] }

export type Rubric = {
  name: string
  format: PostFormat
  share: number
  description: string
  needs_research: boolean
  opinion: boolean
}

export type Strategy = {
  audience: { name: string; pains: string[] }[]
  goal: string
  rubrics: Rubric[]
  forbidden: string[]
  notes: string
}

export type RoleModel = {
  model: string
  fallbacks: string[]
  reasoning: ReasoningLevel
  temperature: number | null
}

export type NewsSchedule = { times: string[]; days: number[]; timezone: string }
export type SmmSchedule = {
  posts_per_week: number
  days: number[]
  windows: { start: string; end: string }[]
  timezone: string
}

export type ChannelOptions = {
  empty_slot_policy: "skip" | "evergreen"
  smm_approval_lead_hours: number
  smm_autopilot_lead_hours: number
  news_lead_minutes: number
  news_approval_window_minutes: number
  plan_auto_approve_hours: number
  max_review_attempts: number
  max_owner_revisions: number
  story_ttl_hours: number
  novelty_window_days: number
  images: boolean
}

export type Channel = {
  id: number
  type: ChannelType
  title: string
  status: ChannelStatus
  publish_mode: PublishMode
  telegram_username: string | null
  telegram_connected: boolean
  brief: Brief
  styleguide: Styleguide
  strategy: Strategy | null
  schedule: NewsSchedule | SmmSchedule
  options: ChannelOptions
  models: Partial<Record<Role, RoleModel>>
  budget_month_usd: number | null
  created_at: string
}

export type SlotStatus =
  | "draft"
  | "approved"
  | "in_production"
  | "awaiting_approval"
  | "scheduled"
  | "published"
  | "skipped"
  | "failed"
  | "deferred"
  | "needs_attention"
  | "not_approved"

export type Slot = {
  id: number
  channel_id: number
  plan_id: number | null
  publish_at: string
  rubric: string
  format: PostFormat
  topic: string
  reader_goal: string
  key_idea: string
  channel_position: string | null
  status: SlotStatus
  locked: boolean
  warnings: { code: string; message: string }[]
  comment: string
  story_id: number | null
  idea_id: number | null
  run_id: string | null
  post_id: number | null
}

export type Plan = {
  id: number
  channel_id: number
  week_start: string
  status: string
  summary: string
  comment: string
  auto_approve_at: string | null
  approved_at: string | null
  run_id: string | null
  slots: Slot[]
}

export type PostStatus =
  | "draft"
  | "awaiting_approval"
  | "scheduled"
  | "published"
  | "failed"
  | "rejected"
  | "needs_attention"

export type Post = {
  id: number
  channel_id: number
  slot_id: number | null
  run_id: string | null
  format: PostFormat
  rubric: string
  title: string
  text: string
  key_idea: string
  status: PostStatus
  publish_at: string | null
  published_at: string | null
  reactions_total: number
  rating: number | null
  media: Record<string, unknown>
  synthetic: boolean
  review_attempts: number
  created_at: string
  cost: number | null
  link: string | null
  body_html?: string
  content?: Record<string, unknown>
  reactions?: Record<string, number>
  poll_results?: Record<string, unknown>
  rating_comment?: string | null
  source_url?: string | null
  writer_text?: string | null
}

export type RunKind = "brief_check" | "onboarding" | "planning" | "post" | "analytics" | "prompt_test" | "channel_rules"
export type RunStatus = "queued" | "running" | "waiting" | "done" | "failed" | "deferred" | "cancelled"

export type Run = {
  id: string
  channel_id: number
  kind: RunKind
  title: string
  status: RunStatus
  current_node: string | null
  current_label: string | null
  slot_id: number | null
  post_id: number | null
  plan_id: number | null
  waiting_for: ({ type: string } & Record<string, unknown>) | null
  result: Record<string, unknown>
  error: string | null
  attempts: number
  next_attempt_at: string | null
  cost_usd: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type RunEvent = {
  seq: number
  ts: string
  type: string
  node: string | null
  data: Record<string, unknown>
}

export type Source = {
  id: number
  url: string
  title: string
  site_url: string | null
  status: "new" | "ok" | "error" | "stale"
  error: string | null
  last_fetched_at: string | null
  last_success_at: string | null
  last_item_at: string | null
  items_total: number
}

export type StoryStatus = "new" | "in_work" | "published" | "rejected" | "expired" | "hidden"

export type StoryItem = {
  title: string
  url: string
  published_at: string | null
  full_text: boolean
  injection: "unchecked" | "clean" | "injection"
  injection_reason: string | null
}

export type FeedCheck = {
  ok: boolean
  error?: string
  url?: string
  title?: string
  site_url?: string | null
  items?: { title: string; url: string; published: string | null; full_text: boolean }[]
}

export type Story = {
  id: number
  story_id: number
  title: string
  status: StoryStatus
  reason: string | null
  priority: boolean
  relevance: number | null
  score: number | null
  score_reason: string | null
  item_count: number
  first_seen_at: string
  last_item_at: string
  related_post_id: number | null
  items: StoryItem[]
}

export type IdeaStatus = "new" | "planned" | "used" | "rejected"

export type Idea = {
  id: number
  rubric: string
  format: PostFormat
  topic: string
  reader_goal: string
  origin: string
  note: string
  vote: number
  status: IdeaStatus
  created_at: string
}

export type AnalyticsReport = {
  id: number
  period_start: string
  period_end: string
  report: Record<string, unknown>
  proposal: Record<string, unknown>
  status: string
  run_id: string | null
  created_at: string
}
