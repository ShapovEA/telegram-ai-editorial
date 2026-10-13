import type {
  ChannelStatus,
  ChannelType,
  IdeaStatus,
  PostFormat,
  PostStatus,
  PublishMode,
  Role,
  RunKind,
  RunStatus,
  SlotStatus,
  StoryStatus,
} from "@/lib/types"

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "muted"

export const channelTypeLabel: Record<ChannelType, string> = {
  news: "Новостной",
  smm: "SMM",
}

export const channelStatusLabel: Record<ChannelStatus, [string, Tone]> = {
  draft: ["Черновик", "muted"],
  onboarding: ["Настройка", "info"],
  active: ["Работает", "success"],
  paused: ["На паузе", "warning"],
}

export const publishModeLabel: Record<PublishMode, string> = {
  autopilot: "Автопилот",
  approval: "С согласованием",
}

export const formatLabel: Record<PostFormat, string> = {
  text: "Текст",
  poll: "Опрос",
  digest: "Дайджест",
}

export const roleLabel: Record<Role, string> = {
  scout: "Скаут",
  chief: "Шеф-редактор",
  factchecker: "Фактчекер",
  researcher: "Расследователь",
  writer: "Писатель",
  editor: "Редактор",
  publisher: "Издатель",
  guard: "Проверка на инъекции",
  novelty: "Проверка новизны",
  strategist: "Стратег",
  account_manager: "Аккаунт-менеджер",
  designer: "Оформитель",
  analyst: "Аналитик",
}

export const slotStatusLabel: Record<SlotStatus, [string, Tone]> = {
  draft: ["Черновик", "muted"],
  approved: ["Утверждён", "info"],
  in_production: ["В работе", "info"],
  awaiting_approval: ["Ждёт согласования", "warning"],
  scheduled: ["Запланирован", "success"],
  published: ["Опубликован", "success"],
  skipped: ["Пропущен", "muted"],
  failed: ["Ошибка", "danger"],
  deferred: ["Отложен", "warning"],
  needs_attention: ["Нужно внимание", "danger"],
  not_approved: ["Не согласован", "danger"],
}

export const postStatusLabel: Record<PostStatus, [string, Tone]> = {
  draft: ["Черновик", "muted"],
  awaiting_approval: ["Ждёт согласования", "warning"],
  scheduled: ["Запланирован", "info"],
  published: ["Опубликован", "success"],
  failed: ["Ошибка", "danger"],
  rejected: ["Отклонён", "muted"],
  needs_attention: ["Нужно внимание", "danger"],
}

export const runKindLabel: Record<RunKind, string> = {
  brief_check: "Проверка брифа",
  onboarding: "Запуск канала",
  planning: "Контент-план",
  post: "Пост",
  analytics: "Аналитика",
  prompt_test: "Тест промпта",
  channel_rules: "Правила канала",
}

export const runStatusLabel: Record<RunStatus, [string, Tone]> = {
  queued: ["В очереди", "muted"],
  running: ["Идёт", "info"],
  waiting: ["Ждёт решения", "warning"],
  done: ["Готово", "success"],
  failed: ["Ошибка", "danger"],
  deferred: ["Повтор позже", "warning"],
  cancelled: ["Остановлен", "muted"],
}

export const storyStatusLabel: Record<StoryStatus, [string, Tone]> = {
  new: ["Новый", "info"],
  in_work: ["В работе", "warning"],
  published: ["Опубликован", "success"],
  rejected: ["Отклонён", "muted"],
  expired: ["Устарел", "muted"],
  hidden: ["Скрыт", "muted"],
}

export const ideaStatusLabel: Record<IdeaStatus, [string, Tone]> = {
  new: ["Новая", "info"],
  planned: ["В плане", "warning"],
  used: ["Использована", "success"],
  rejected: ["Отклонена", "muted"],
}

export const weekdayShort = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
