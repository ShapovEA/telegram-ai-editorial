import type { Brief, ChannelType } from "@/lib/types"

export type BriefTextField = "about" | "audience" | "goal" | "voice" | "avoid" | "positions"

export type FieldCopy = { label: string; hint: string; placeholder: string }

type Spec = { fields: BriefTextField[]; required: BriefTextField[]; copy: Record<BriefTextField, FieldCopy> }

const SMM_COPY: Record<BriefTextField, FieldCopy> = {
  about: {
    label: "О чём канал",
    hint: "Тема, угол зрения, чем канал отличается от соседних",
    placeholder: "Канал о личных финансах для тех, кто только начал копить: без сложных терминов и обещаний быстрых денег",
  },
  audience: {
    label: "Для кого",
    hint: "Кто читает, что уже знает, чего хочет",
    placeholder: "Люди 25–35 лет с первой стабильной зарплатой, которые не понимают, куда девать деньги",
  },
  goal: {
    label: "Цель канала",
    hint: "Что должно происходить с читателем или бизнесом благодаря каналу",
    placeholder: "Чтобы читатели собрали финансовую подушку и записывались на нашу консультацию",
  },
  voice: {
    label: "Как говорить",
    hint: "Тон, обращение, примеры фраз, которые звучат «как вы»",
    placeholder: "На «ты», спокойно, с примерами из жизни. Можно «я тоже так ошибался», нельзя «уважаемые подписчики»",
  },
  avoid: {
    label: "Чего избегать",
    hint: "Темы, слова и приёмы, которых в канале быть не должно",
    placeholder: "Не обещать доходность, не советовать конкретные акции, без кликбейта",
  },
  positions: {
    label: "Позиции канала",
    hint: "Во что канал верит и с чем спорит. Без них отдел не пишет мнения",
    placeholder: "Подушка безопасности важнее инвестиций. Долги по кредитным картам гасим первыми",
  },
}

const NEWS_COPY: Record<BriefTextField, FieldCopy> = {
  ...SMM_COPY,
  about: {
    label: "О чём канал",
    hint: "Какую область освещает канал и какие события в ней важны",
    placeholder: "Новости бухгалтерского учёта и налогов в России: изменения законов, разъяснения ФНС и Минфина, сроки отчётности",
  },
  audience: {
    label: "Для кого",
    hint: "Кто читает и что ему нужно от новостей",
    placeholder: "Бухгалтеры малого и среднего бизнеса: им важно быстро понять, что изменилось и что теперь делать",
  },
}

export const BRIEF_SPEC: Record<ChannelType, Spec> = {
  news: { fields: ["about", "audience"], required: ["about", "audience"], copy: NEWS_COPY },
  smm: {
    fields: ["about", "audience", "goal", "voice", "avoid", "positions"],
    required: ["about", "audience", "goal", "voice", "avoid"],
    copy: SMM_COPY,
  },
}

export function briefMissing(brief: Brief, type: ChannelType): BriefTextField[] {
  return BRIEF_SPEC[type].required.filter((k) => !brief[k].trim())
}

export type SampleKind = "channel" | "post" | "page" | "text"

export function sampleKind(item: string): SampleKind {
  const v = item.trim()
  if (/^(?:https?:\/\/)?t\.me\/(?:s\/)?[A-Za-z0-9_]{4,64}\/\d+\/?(?:\?.*)?$/.test(v)) return "post"
  if (/^(?:(?:https?:\/\/)?t\.me\/(?:s\/)?|@)[A-Za-z0-9_]{4,64}\/?$/.test(v)) return "channel"
  if (/^https?:\/\/\S+$/.test(v)) return "page"
  return "text"
}
