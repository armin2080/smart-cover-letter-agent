import type { TourStep } from "./Tour"

/**
 * The tour shown the first time a user reaches the workspace.
 *
 * Every target lives in the persistent shell, so the tour never has to navigate
 * and cannot end up pointing at an element that has not rendered yet. Steps are
 * intentionally few: the goal is orientation, not documentation.
 */
export const WORKSPACE_TOUR: TourStep[] = [
  {
    title: "Welcome to SmartCover",
    body:
      "A thirty-second look around, so you know where everything lives. You can leave at any point and it will not ask again.",
  },
  {
    anchor: "nav-overview",
    placement: "right",
    title: "Your overview",
    body:
      "Recent matches, your search activity and anything waiting on you. This is where a session usually starts.",
  },
  {
    anchor: "nav-find",
    placement: "right",
    title: "Find jobs",
    body:
      "Run a search across your sources. You choose the job titles, locations and employment types, and we keep only what fits your profile.",
  },
  {
    anchor: "nav-jobs",
    placement: "right",
    title: "My jobs",
    body:
      "Everything collected, with an explanation of why each role matches. Save what interests you, dismiss the rest, and the count on the badge keeps track.",
  },
  {
    anchor: "nav-profile",
    placement: "right",
    title: "Your CV and profile",
    body:
      "Upload a CV and we extract skills, experience and education. Matching compares every listing against what is in here, so keeping it current is worth the effort.",
  },
  {
    anchor: "nav-settings",
    placement: "right",
    title: "Settings",
    body:
      "Automatic search, notifications and your account. You can leave the searching to us and just review what turns up.",
  },
  {
    anchor: "topbar-notifications",
    placement: "below",
    title: "Stay in the loop",
    body:
      "New matches and finished searches appear here, so you do not have to keep checking the lists.",
  },
  {
    title: "That's everything",
    body:
      "Start with Find Jobs, or add a listing yourself if you have already spotted something. You can repeat this tour any time from Settings.",
  },
]
