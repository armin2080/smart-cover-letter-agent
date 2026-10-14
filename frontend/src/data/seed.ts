/**
 * Seed data for the in-browser mock transport.
 *
 * All names, companies, figures and dates are illustrative sample data.
 */

import { companyColor } from "../lib/format"
import type {
  ActivityEntry,
  AutoSearchSettings,
  CoverLetter,
  JobDetail,
  MatchAnalysis,
  MatchLine,
  NotificationSettings,
  Preferences,
  Profile,
  SearchRun,
  User,
} from "../types/api"

const hoursAgo = (hours: number): string => new Date(Date.now() - hours * 3_600_000).toISOString()
const daysAgo = (days: number): string => hoursAgo(days * 24)

function line(positive: boolean, title: string, detail: string): MatchLine {
  return { positive, title, detail }
}

const STRONG: MatchAnalysis = {
  cvAlignment: [
    line(true, "Strong product design background", "Your 5+ years meets their seniority requirement."),
    line(true, "4 key skills found in your CV", "Figma, design systems, prototyping and research."),
    line(true, "Relevant B2B SaaS experience", "Your work at Studio Nord closely relates."),
    line(false, "Fintech domain experience", "Not found in your CV, listed as a nice-to-have."),
  ],
  preferenceFit: [
    line(true, "Preferred job title", "Product Designer is one of your target roles."),
    line(true, "Location compatible", "Berlin is within your 50 km radius."),
    line(true, "Employment type matches", "You prefer full-time positions."),
    line(true, "Preferred source", "LinkedIn is enabled in your settings."),
  ],
}

const GOOD: MatchAnalysis = {
  cvAlignment: [
    line(true, "Relevant design experience", "Your background aligns with the core responsibilities."),
    line(true, "3 key skills found in your CV", "Figma, prototyping and user research."),
    line(false, "Industry experience", "Sector experience is limited in your current CV."),
    line(false, "Team leadership", "Not evidenced in your CV, but listed as desirable."),
  ],
  preferenceFit: [
    line(true, "Preferred job title", "Matches one of your saved target roles."),
    line(true, "Employment type matches", "Compatible with your preferences."),
    line(false, "Location", "Slightly outside your usual commute radius."),
    line(true, "Preferred source", "Enabled in your settings."),
  ],
}

const POTENTIAL: MatchAnalysis = {
  cvAlignment: [
    line(true, "Transferable skills", "Several of your skills appear relevant."),
    line(false, "Core requirement gap", "A primary requirement is not present in your CV."),
    line(false, "Seniority difference", "The role may target a different level."),
    line(false, "Domain knowledge", "No matching domain experience found."),
  ],
  preferenceFit: [
    line(true, "Preferred source", "Enabled in your settings."),
    line(false, "Employment type", "This role is part-time, you prefer full-time."),
    line(false, "Location", "Outside your preferred locations."),
    line(false, "Job title", "Not one of your target roles."),
  ],
}

interface JobSeed {
  id: number
  title: string
  company: string
  location: string
  employmentType: string
  hours: number
  source: string
  match: JobDetail["match"]
  status: JobDetail["status"]
  skills: string[]
  hasCoverLetter: boolean
  summary: string
  responsibilities: string[]
  requirements: string[]
  analysis: MatchAnalysis
}

const JOB_SEEDS: JobSeed[] = [
  {
    id: 1,
    title: "Product Designer",
    company: "Northstar Labs",
    location: "Berlin, Germany",
    employmentType: "full-time",
    hours: 2,
    source: "LinkedIn",
    match: "strong",
    status: "new",
    skills: ["Figma", "Design systems", "Research"],
    hasCoverLetter: true,
    summary:
      "Shape thoughtful digital products used by ambitious teams across Europe, working closely with product, engineering and research.",
    responsibilities: [
      "Lead end-to-end product design from discovery through polished delivery.",
      "Partner with product managers and engineers to define opportunities.",
      "Develop and evolve a scalable, accessible design system.",
      "Plan user research and translate insights into product improvements.",
    ],
    requirements: [
      "4+ years designing digital products in a collaborative environment.",
      "A portfolio demonstrating strong systems thinking and craft.",
      "Advanced proficiency in Figma and prototyping tools.",
      "Clear communication in English; German is a plus.",
    ],
    analysis: STRONG,
  },
  {
    id: 2,
    title: "Senior UX Designer",
    company: "Morrow",
    location: "Remote · Germany",
    employmentType: "full-time",
    hours: 24,
    source: "StepStone",
    match: "strong",
    status: "saved",
    skills: ["Product strategy", "Prototyping", "SaaS"],
    hasCoverLetter: false,
    summary:
      "Own the experience of a fast-growing B2B platform and help define how teams collaborate across Europe.",
    responsibilities: [
      "Define experience strategy for a core product area.",
      "Prototype and validate concepts with customers.",
      "Raise the bar for interaction and visual craft.",
    ],
    requirements: [
      "5+ years of UX or product design experience.",
      "Experience working in a SaaS environment.",
      "Strong facilitation and communication skills.",
    ],
    analysis: STRONG,
  },
  {
    id: 3,
    title: "Digital Product Designer",
    company: "Fern & Co.",
    location: "Hamburg, Germany",
    employmentType: "full-time",
    hours: 48,
    source: "Stellenwerk",
    match: "good",
    status: "new",
    skills: ["UI design", "Workshops", "Agile"],
    hasCoverLetter: false,
    summary:
      "Join a multidisciplinary studio delivering digital products for clients across retail and logistics.",
    responsibilities: [
      "Design interfaces for client products across web and mobile.",
      "Run discovery workshops with stakeholders.",
      "Collaborate within an agile delivery team.",
    ],
    requirements: [
      "3+ years of product or UI design experience.",
      "Comfortable presenting work to clients.",
      "Working knowledge of design systems.",
    ],
    analysis: GOOD,
  },
  {
    id: 4,
    title: "UX/UI Designer",
    company: "Orbit Health",
    location: "Munich, Germany",
    employmentType: "part-time",
    hours: 72,
    source: "LinkedIn",
    match: "potential",
    status: "reviewed",
    skills: ["Mobile", "Healthcare", "Figma"],
    hasCoverLetter: true,
    summary:
      "Improve patient-facing experiences for a digital health platform used across clinics.",
    responsibilities: [
      "Design accessible mobile flows for patient onboarding.",
      "Maintain component libraries in Figma.",
      "Support usability testing sessions.",
    ],
    requirements: [
      "Experience designing regulated or clinical products.",
      "Strong accessibility knowledge.",
      "Part-time availability (20 hours per week).",
    ],
    analysis: POTENTIAL,
  },
  {
    id: 5,
    title: "Product Designer — Growth",
    company: "Ledgerly",
    location: "Remote · EU",
    employmentType: "full-time",
    hours: 96,
    source: "StepStone",
    match: "good",
    status: "dismissed",
    skills: ["Growth", "Analytics", "B2B"],
    hasCoverLetter: false,
    summary: "Drive experimentation and conversion across a finance platform for small businesses.",
    responsibilities: [
      "Design and analyse growth experiments.",
      "Partner with data and marketing teams.",
      "Iterate on onboarding and activation flows.",
    ],
    requirements: [
      "Experience designing for measurable growth outcomes.",
      "Comfortable working with analytics tooling.",
      "Fintech experience preferred.",
    ],
    analysis: GOOD,
  },
  {
    id: 6,
    title: "Senior Product Designer",
    company: "Aperture Software",
    location: "Berlin, Germany",
    employmentType: "full-time",
    hours: 6,
    source: "LinkedIn",
    match: "strong",
    status: "new",
    skills: ["Design systems", "Accessibility", "Figma"],
    hasCoverLetter: false,
    summary: "Lead design for a developer tooling platform with a strong emphasis on accessibility.",
    responsibilities: [
      "Own the design system and accessibility standards.",
      "Mentor mid-level designers.",
      "Drive cross-functional design reviews.",
    ],
    requirements: [
      "5+ years of product design experience.",
      "Deep familiarity with WCAG guidelines.",
      "Experience maintaining a design system.",
    ],
    analysis: STRONG,
  },
  {
    id: 7,
    title: "UX Researcher",
    company: "Cobalt Analytics",
    location: "Remote · Germany",
    employmentType: "full-time",
    hours: 30,
    source: "Stellenwerk",
    match: "good",
    status: "new",
    skills: ["User research", "Interviews", "Synthesis"],
    hasCoverLetter: false,
    summary: "Build the research practice for a data analytics product used by enterprise teams.",
    responsibilities: [
      "Plan and run qualitative research studies.",
      "Synthesise findings into actionable insights.",
      "Establish repeatable research processes.",
    ],
    requirements: [
      "3+ years in a research-focused role.",
      "Strong qualitative research toolkit.",
      "Experience influencing product direction.",
    ],
    analysis: GOOD,
  },
  {
    id: 8,
    title: "Design System Lead",
    company: "Vertex Commerce",
    location: "Berlin, Germany",
    employmentType: "full-time",
    hours: 54,
    source: "LinkedIn",
    match: "strong",
    status: "saved",
    skills: ["Design systems", "Tokens", "Documentation"],
    hasCoverLetter: false,
    summary: "Own a cross-product design system and the tooling that supports it.",
    responsibilities: [
      "Define and maintain design tokens and component APIs.",
      "Partner with engineering on library releases.",
      "Grow adoption across product teams.",
    ],
    requirements: [
      "Experience leading a design system.",
      "Working knowledge of front-end implementation.",
      "Excellent documentation skills.",
    ],
    analysis: STRONG,
  },
  {
    id: 9,
    title: "Interaction Designer",
    company: "Halcyon Studio",
    location: "Potsdam, Germany",
    employmentType: "working-student",
    hours: 120,
    source: "Stellenwerk",
    match: "potential",
    status: "reviewed",
    skills: ["Motion", "Prototyping", "Figma"],
    hasCoverLetter: false,
    summary: "Support senior designers on interactive prototypes for cultural and public-sector clients.",
    responsibilities: [
      "Build high-fidelity interactive prototypes.",
      "Explore motion and micro-interaction detail.",
      "Assist with client presentations.",
    ],
    requirements: [
      "Currently enrolled in a design programme.",
      "Strong Figma and prototyping skills.",
      "Available 16–20 hours per week.",
    ],
    analysis: POTENTIAL,
  },
]

export const SEED_JOBS: JobDetail[] = JOB_SEEDS.map((seed) => ({
  id: seed.id,
  title: seed.title,
  company: seed.company,
  companyInitials: seed.company
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase(),
  companyColor: companyColor(seed.company),
  location: seed.location,
  employmentType: seed.employmentType,
  postedAt: hoursAgo(seed.hours),
  source: seed.source,
  sourceUrl: `https://example.com/jobs/${seed.id}`,
  match: seed.match,
  status: seed.status,
  skills: seed.skills,
  hasCoverLetter: seed.hasCoverLetter,
  summary: seed.summary,
  responsibilities: seed.responsibilities,
  requirements: seed.requirements,
  analysis: seed.analysis,
}))

export const SEED_USER: User = {
  id: 1,
  email: "armin.keller@example.com",
  fullName: "Armin Keller",
  createdAt: daysAgo(120),
}

export const SEED_PROFILE: Profile = {
  fullName: "Armin Keller",
  email: "armin.keller@example.com",
  phone: "+49 151 234 5678",
  location: "Berlin, Germany",
  portfolio: "arminkeller.example.com",
  summary:
    "Product designer with 5+ years creating intuitive B2B and consumer experiences, focused on design systems and research-led product work.",
  cv: {
    id: 1,
    fileName: "armin-keller-cv.pdf",
    sizeBytes: 1_258_291,
    uploadedAt: daysAgo(12),
    url: null,
    status: "ready",
  },
  sections: [
    {
      id: "personal",
      key: "personal",
      title: "Personal information",
      content: "Armin Keller · Berlin, Germany · armin.keller@example.com",
    },
    {
      id: "summary",
      key: "summary",
      title: "Professional summary",
      content:
        "Product designer with 5+ years creating intuitive B2B and consumer experiences.",
    },
    {
      id: "experience",
      key: "experience",
      title: "Work experience",
      content:
        "Senior Product Designer at Studio Nord · 2021–Present\nProduct Designer at Kollektiv · 2019–2021",
    },
    {
      id: "education",
      key: "education",
      title: "Education",
      content: "M.A. Interaction Design, UDK Berlin · 2019",
    },
    {
      id: "skills",
      key: "skills",
      title: "Skills",
      content: "Figma, Product strategy, Design systems, User research, Prototyping",
    },
    {
      id: "projects",
      key: "projects",
      title: "Projects",
      content: "Flowline Design System · Studio Nord",
    },
    {
      id: "languages",
      key: "languages",
      title: "Languages",
      content: "German (Native), English (Fluent)",
    },
    {
      id: "certificates",
      key: "certificates",
      title: "Certificates",
      content: "NN/g UX Certification · 2022",
    },
  ],
}

export const SEED_PREFERENCES: Preferences = {
  desiredRoles: ["Product Designer", "Senior UX Designer"],
  locations: ["Berlin", "Remote (Germany)"],
  radiusKm: 50,
  employmentTypes: ["full-time"],
  sources: ["LinkedIn", "StepStone", "Stellenwerk"],
  keywords: ["SaaS", "design systems", "B2B"],
}

export const SEED_COVER_LETTER: CoverLetter = {
  id: 1,
  jobId: 1,
  content: `Dear Northstar Labs Hiring Team,

I am writing to express my interest in the Product Designer position at Northstar Labs. With more than five years of experience designing thoughtful B2B products and scalable design systems, I am excited by the opportunity to help simplify complex workflows for your customers.

In my current role at Studio Nord, I lead end-to-end design across a suite of collaboration tools used by more than 40,000 professionals. I recently redesigned our core onboarding experience, partnering closely with product and engineering to increase activation by 22%. I also established a shared design system that improved consistency and reduced delivery time across three product teams.

Northstar's focus on purposeful, human-centered tools particularly resonates with me. My background in research, interaction design and cross-functional facilitation would allow me to contribute quickly while continuing to grow alongside your team.

I would welcome the opportunity to discuss how my experience could support Northstar's next stage of product growth. Thank you for your consideration.

Sincerely,
Armin Keller`,
  language: "English",
  tone: "professional",
  length: "balanced",
  status: "saved",
  updatedAt: hoursAgo(20),
  savedAt: hoursAgo(20),
}

export const SEED_ACTIVITY: ActivityEntry[] = [
  {
    id: 1,
    kind: "discovered",
    title: "12 jobs discovered",
    subtitle: "Automatic search · Today, 08:30",
    occurredAt: hoursAgo(5),
  },
  {
    id: 2,
    kind: "reviewed",
    title: "Product Designer reviewed",
    subtitle: "Northstar Labs · Yesterday",
    occurredAt: hoursAgo(20),
  },
  {
    id: 3,
    kind: "saved",
    title: "Senior UX Designer saved",
    subtitle: "Morrow · Monday",
    occurredAt: daysAgo(3),
  },
  {
    id: 4,
    kind: "cover-letter",
    title: "Cover letter generated",
    subtitle: "Orbit Health · Friday",
    occurredAt: daysAgo(4),
  },
]

export const SEED_SEARCH_HISTORY: SearchRun[] = [
  {
    id: 101,
    mode: "automatic",
    status: "completed",
    startedAt: hoursAgo(5),
    finishedAt: hoursAgo(4.9),
    criteriaSummary: "Product Designer · Berlin · 50 km",
    sources: ["LinkedIn", "StepStone", "Stellenwerk"],
    discovered: 42,
    matched: 12,
    stages: [],
    error: null,
  },
  {
    id: 102,
    mode: "automatic",
    status: "completed",
    startedAt: daysAgo(1.2),
    finishedAt: daysAgo(1.19),
    criteriaSummary: "Product Designer · Berlin · 50 km",
    sources: ["LinkedIn", "StepStone", "Stellenwerk"],
    discovered: 38,
    matched: 5,
    stages: [],
    error: null,
  },
  {
    id: 103,
    mode: "manual",
    status: "completed",
    startedAt: daysAgo(4),
    finishedAt: daysAgo(4),
    criteriaSummary: "UX Research roles · Remote · 25 km",
    sources: ["LinkedIn", "Stellenwerk"],
    discovered: 51,
    matched: 8,
    stages: [],
    error: null,
  },
  {
    id: 104,
    mode: "automatic",
    status: "failed",
    startedAt: daysAgo(6),
    finishedAt: daysAgo(6),
    criteriaSummary: "Product Designer · Berlin · 50 km",
    sources: ["LinkedIn", "StepStone", "Stellenwerk"],
    discovered: 0,
    matched: 0,
    stages: [],
    error: "StepStone did not respond in time. Other sources completed successfully.",
  },
]

export const SEED_AUTO_SETTINGS: AutoSearchSettings = {
  enabled: true,
  frequency: "daily",
  timeOfDay: "08:30",
  weekday: null,
  sources: ["LinkedIn", "StepStone", "Stellenwerk"],
  status: "active",
  lastRunAt: hoursAgo(5),
  nextRunAt: new Date(new Date().setHours(8, 30, 0, 0) + 24 * 3_600_000).toISOString(),
}

export const SEED_NOTIFICATIONS: NotificationSettings = {
  newMatches: true,
  searchCompleted: true,
  searchFailures: true,
}
