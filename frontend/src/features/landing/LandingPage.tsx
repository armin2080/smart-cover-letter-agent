import { useNavigate } from "react-router-dom"
import { useAuth } from "../../app/AuthProvider"
import { useConfig } from "../../app/ConfigProvider"
import { Button } from "../../components/ui/Button"
import { Badge, Company, Logo } from "../../components/ui/Common"
import { Icon } from "../../components/ui/Icon"
import type { Job } from "../../types"

/**
 * Marketing preview data.
 *
 * The landing page is public, so it does not call the authenticated API.
 * These entries are illustrative sample data used purely to visualise the
 * product inside the hero and feature sections.
 */
const PREVIEW_JOBS: Job[] = [
  {
    id: -1,
    title: "Product Designer",
    company: "Northstar Labs",
    companyInitials: "NL",
    companyColor: "#172333",
    location: "Berlin, Germany",
    employmentType: "full-time",
    postedAt: new Date().toISOString(),
    source: "LinkedIn",
    sourceUrl: "#",
    match: "strong",
    status: "new",
    skills: ["Figma", "Design systems", "Research"],
    hasCoverLetter: false,
  },
  {
    id: -2,
    title: "Senior UX Designer",
    company: "Morrow",
    companyInitials: "M",
    companyColor: "#299B8D",
    location: "Remote · Germany",
    employmentType: "full-time",
    postedAt: new Date().toISOString(),
    source: "StepStone",
    sourceUrl: "#",
    match: "strong",
    status: "new",
    skills: ["Product strategy", "Prototyping", "SaaS"],
    hasCoverLetter: false,
  },
  {
    id: -3,
    title: "Digital Product Designer",
    company: "Fern & Co.",
    companyInitials: "FC",
    companyColor: "#765B44",
    location: "Hamburg, Germany",
    employmentType: "full-time",
    postedAt: new Date().toISOString(),
    source: "Stellenwerk",
    sourceUrl: "#",
    match: "good",
    status: "new",
    skills: ["UI design", "Workshops", "Agile"],
    hasCoverLetter: false,
  },
]

const STEPS: Array<[string, string, string]> = [
  [
    "01",
    "Build your profile",
    "Upload your CV once. We organise your experience, skills and preferences.",
  ],
  [
    "02",
    "Discover your best matches",
    "Search trusted sources and see clearly why each role fits your background.",
  ],
  [
    "03",
    "Prepare a strong application",
    "Generate and refine a tailored cover letter in a professional editor.",
  ],
]

function ProductPreview() {
  const job = PREVIEW_JOBS[0]
  return (
    <div className="product-preview" aria-hidden="true">
      <div className="preview-side">
        <Logo compact />
        <i />
        <i />
        <i />
        <i />
      </div>
      <div className="preview-main">
        <div className="preview-bar">
          <span>My Jobs</span>
          <span>⌕ &nbsp; ●</span>
        </div>
        <div className="preview-content">
          <div className="preview-list">
            <b>New matches</b>
            {PREVIEW_JOBS.map((entry, index) => (
              <div className={`preview-row ${index === 0 ? "active" : ""}`} key={entry.id}>
                <Company job={entry} />
                <span>
                  <b>{entry.title}</b>
                  <small>
                    {entry.company} · {entry.location}
                  </small>
                  <em>
                    <Badge match={entry.match} />
                  </em>
                </span>
              </div>
            ))}
          </div>
          <div className="preview-detail">
            <div className="match-job">
              <Company job={job} large />
              <div>
                <h3>{job.title}</h3>
                <p>
                  {job.company} · Berlin
                </p>
              </div>
            </div>
            <Badge match="strong" />
            <h4>Why this job matches you</h4>
            <div className="preview-check">
              <Icon name="check" /> Your product design experience aligns closely
            </div>
            <div className="preview-check">
              <Icon name="check" /> 4 of 5 core skills found in your CV
            </div>
            <div className="preview-check">
              <Icon name="check" /> Location and employment type match
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function LandingPage() {
  const navigate = useNavigate()
  const { status } = useAuth()
  const { config } = useConfig()

  // When registration is closed the only useful destination is the login
  // screen: an account has to be created by an administrator first.
  const registrationOpen = config.registrationEnabled
  const primaryTarget = status === "authenticated" ? "/overview" : registrationOpen ? "/register" : "/login"

  return (
    <div className="landing">
      <nav className="land-nav">
        <Logo />
        <div className="land-links">
          <a href="#how">How it works</a>
          <a href="#features">Features</a>
          <a href="#matching">Matching</a>
        </div>
        <div className="nav-actions">
          {status === "authenticated" ? (
            <Button onClick={() => navigate("/overview")}>Go to workspace</Button>
          ) : (
            <>
              <Button kind="ghost" onClick={() => navigate("/login")}>
                Log in
              </Button>
              {registrationOpen && (
                <Button onClick={() => navigate("/register")}>Get started</Button>
              )}
            </>
          )}
        </div>
      </nav>

      <main>
        <section className="hero">
          <div className="eyebrow">
            <Icon name="sparkle" size={14} /> Your next opportunity, intelligently matched
          </div>
          <h1>
            Find opportunities that
            <br />
            actually fit you.
          </h1>
          <p>
            Discover relevant jobs, understand why they match your experience, and prepare personalized
            applications with AI.
          </p>
          <div className="hero-actions">
            <Button onClick={() => navigate(primaryTarget)}>
              {status === "authenticated" ? "Go to Workspace" : registrationOpen ? "Get Started" : "Log In"}{" "}
              <Icon name="arrow" size={16} />
            </Button>
            <Button
              kind="secondary"
              onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}
            >
              See How It Works
            </Button>
          </div>
          <div className="trust">
            <span>
              <Icon name="check" size={14} /> No credit card required
            </span>
            <span>
              <Icon name="shield" size={14} /> Your data stays private
            </span>
          </div>
        </section>

        <ProductPreview />

        <section className="steps-section" id="how">
          <div className="section-head">
            <span>HOW IT WORKS</span>
            <h2>From CV to tailored application</h2>
            <p>A focused workflow that does the busywork while keeping you in control.</p>
          </div>
          <div className="steps">
            {STEPS.map(([number, title, description]) => (
              <div className="step" key={number}>
                <span>{number}</span>
                <h3>{title}</h3>
                <p>{description}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="feature-grid" id="features">
          <div className="feature-copy">
            <span className="overline">A BETTER WAY TO SEARCH</span>
            <h2>All the context you need, without the noise.</h2>
            <p>
              SmartCover brings job discovery, fit analysis and application preparation into one calm
              workspace.
            </p>
            <ul>
              <li>
                <Icon name="check" /> Search LinkedIn, StepStone and Stellenwerk together
              </li>
              <li>
                <Icon name="check" /> Compare every role against your actual experience
              </li>
              <li>
                <Icon name="check" /> Keep new, reviewed and saved roles organised
              </li>
            </ul>
          </div>
          <div className="mini-ui">
            <div className="mini-top">
              Recent matches <span>View all</span>
            </div>
            {PREVIEW_JOBS.map((job) => (
              <div className="mini-job" key={job.id}>
                <Company job={job} />
                <div>
                  <strong>{job.title}</strong>
                  <small>
                    {job.company} · {job.location}
                  </small>
                </div>
                <Badge match={job.match} />
              </div>
            ))}
          </div>
        </section>

        <section className="match-section" id="matching">
          <div className="section-head">
            <span>INTELLIGENT MATCHING</span>
            <h2>Know why a role is worth your time.</h2>
          </div>
          <div className="match-card">
            <div className="match-job">
              <Company job={PREVIEW_JOBS[0]} large />
              <div>
                <h3>{PREVIEW_JOBS[0].title}</h3>
                <p>{PREVIEW_JOBS[0].company} · Berlin</p>
              </div>
              <Badge match="strong" />
            </div>
            <div className="alignment">
              <div>
                <b>CV Alignment</b>
                <p>
                  <Icon name="check" /> 5 years of product design experience
                </p>
                <p>
                  <Icon name="check" /> Strong design systems background
                </p>
                <p className="weak">○ Limited fintech experience</p>
              </div>
              <div>
                <b>Preference Fit</b>
                <p>
                  <Icon name="check" /> Berlin is within your search area
                </p>
                <p>
                  <Icon name="check" /> Full-time role matches preference
                </p>
                <p>
                  <Icon name="check" /> Desired role: Product Designer
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="letter-feature">
          <div className="letter-paper">
            <span>Dear Northstar team,</span>
            <p>
              I am excited to apply for the Product Designer position. With five years of experience creating
              thoughtful B2B products and scalable design systems, I see a strong alignment...
            </p>
            <span>
              Sincerely,
              <br />
              Armin Keller
            </span>
          </div>
          <div className="feature-copy">
            <span className="overline">AI-ASSISTED WRITING</span>
            <h2>A tailored first draft, ready for your voice.</h2>
            <p>
              Start with a cover letter grounded in your CV and the role. Edit every word, adjust tone and
              export when it feels right.
            </p>
            <Button onClick={() => navigate(primaryTarget)}>Create your first letter</Button>
          </div>
        </section>

        <section className="final-cta">
          <span className="eyebrow">START YOUR SEARCH</span>
          <h2>Make your next application count.</h2>
          <p>Spend less time sorting through roles and more time pursuing the right ones.</p>
          <Button onClick={() => navigate(primaryTarget)}>
            {registrationOpen ? "Get started for free" : "Log in to your workspace"}{" "}
            <Icon name="arrow" size={16} />
          </Button>
        </section>
      </main>

      <footer>
        <Logo />
        <p>Intelligent job search and application preparation.</p>
        <div>
          <a>Privacy</a>
          <a>Terms</a>
          <a>Contact</a>
        </div>
        <small>© {new Date().getFullYear()} SmartCover · Sample content for demonstration</small>
      </footer>
    </div>
  )
}
