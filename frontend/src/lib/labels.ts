import type { EmploymentType, JobStatus, MatchLevel } from "../types/api"

/** Qualitative match labels — deliberately never a percentage. */
export function matchLabel(level: MatchLevel): string {
  switch (level) {
    case "strong":
      return "Strong match"
    case "good":
      return "Good match"
    default:
      return "Potential match"
  }
}

export function matchClass(level: MatchLevel): string {
  return `${level}-match`
}

export function statusLabel(status: JobStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

export function employmentLabel(type: EmploymentType | string): string {
  switch (type) {
    case "full-time":
      return "Full-time"
    case "part-time":
      return "Part-time"
    case "working-student":
      return "Working student"
    case "internship":
      return "Internship"
    case "minijob":
      return "Minijob"
    default:
      return String(type)
  }
}

export const EMPLOYMENT_OPTIONS: Array<{ value: EmploymentType; label: string }> = [
  { value: "full-time", label: "Full-time" },
  { value: "part-time", label: "Part-time" },
  { value: "working-student", label: "Working student" },
  { value: "internship", label: "Internship" },
  { value: "minijob", label: "Minijob" },
]

export const SOURCE_OPTIONS = ["LinkedIn", "StepStone", "Stellenwerk"]

export const MATCH_OPTIONS: Array<{ value: MatchLevel; label: string }> = [
  { value: "strong", label: "Strong match" },
  { value: "good", label: "Good match" },
  { value: "potential", label: "Potential match" },
]

export const TONE_OPTIONS = ["professional", "confident", "warm"] as const
export const LENGTH_OPTIONS = ["concise", "balanced", "detailed"] as const
export const LANGUAGE_OPTIONS = ["English", "German"]

export function toneLabel(tone: string): string {
  return tone.charAt(0).toUpperCase() + tone.slice(1)
}

export function lengthLabel(length: string): string {
  switch (length) {
    case "concise":
      return "Concise · ~250 words"
    case "detailed":
      return "Detailed · ~500 words"
    default:
      return "Balanced · ~350 words"
  }
}

export function greeting(now: Date = new Date()): string {
  const hour = now.getHours()
  if (hour < 12) return "Good morning"
  if (hour < 18) return "Good afternoon"
  return "Good evening"
}
