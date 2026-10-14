import { useState, type FormEvent } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { useAuth } from "../../app/AuthProvider"
import { Button } from "../../components/ui/Button"
import { Logo } from "../../components/ui/Common"
import { Field } from "../../components/ui/Field"
import { normalizeError } from "../../lib/errors"

interface AuthPageProps {
  mode: "login" | "register"
}

interface FormState {
  fullName: string
  email: string
  password: string
  passwordConfirm: string
  acceptedTerms: boolean
  remember: boolean
}

const EMPTY_FORM: FormState = {
  fullName: "",
  email: "",
  password: "",
  passwordConfirm: "",
  acceptedTerms: false,
  remember: true,
}

export function AuthPage({ mode }: AuthPageProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, register } = useAuth()

  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const isRegister = mode === "register"

  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/overview"

  const clientErrors = (): Record<string, string[]> => {
    const errors: Record<string, string[]> = {}
    if (isRegister && form.fullName.trim().length < 2) {
      errors.fullName = ["Please enter your full name."]
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      errors.email = ["Enter a valid email address."]
    }
    if (form.password.length < 8) {
      errors.password = ["Use at least 8 characters."]
    }
    if (isRegister && form.password !== form.passwordConfirm) {
      errors.passwordConfirm = ["Passwords do not match."]
    }
    if (isRegister && !form.acceptedTerms) {
      errors.acceptedTerms = ["Please accept the terms to continue."]
    }
    return errors
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    setError(null)

    const localErrors = clientErrors()
    if (Object.keys(localErrors).length) {
      setFieldErrors(localErrors)
      return
    }

    setFieldErrors({})
    setSubmitting(true)

    try {
      if (isRegister) {
        await register({
          fullName: form.fullName.trim(),
          email: form.email.trim(),
          password: form.password,
          passwordConfirm: form.passwordConfirm,
          acceptedTerms: form.acceptedTerms,
        })
        navigate("/onboarding", { replace: true })
      } else {
        await login({ email: form.email.trim(), password: form.password, remember: form.remember })
        navigate(redirectTo, { replace: true })
      }
    } catch (caught) {
      const apiError = normalizeError(caught)
      setFieldErrors(apiError.fieldErrors ?? {})
      setError(apiError.displayMessage)
    } finally {
      setSubmitting(false)
    }
  }

  const errorFor = (field: keyof FormState): string | undefined => {
    if (fieldErrors[field]?.length) return fieldErrors[field][0]
    return undefined
  }

  return (
    <div className="auth-page">
      <div className="auth-brand">
        <Logo />
        <div>
          <span className="eyebrow">YOUR CAREER WORKSPACE</span>
          <h1>Better opportunities begin with better context.</h1>
          <p>
            One calm place to discover relevant roles, understand your fit, and prepare applications that
            sound like you.
          </p>
        </div>
        <small>Illustrative product preview · sample data only.</small>
      </div>

      <div className="auth-form-wrap">
        <button className="back-link" onClick={() => navigate("/")}>
          ← Back to home
        </button>

        <form className="auth-card" onSubmit={submit} noValidate>
          <h2>{isRegister ? "Create your account" : "Welcome back"}</h2>
          <p>
            {isRegister
              ? "Start finding opportunities that fit your experience."
              : "Continue your job search where you left off."}
          </p>

          {error && (
            <div className="error-banner" role="alert" style={{ marginBottom: 16 }}>
              <span>{error}</span>
            </div>
          )}

          {isRegister && (
            <Field
              label="Full name"
              placeholder="Armin Keller"
              value={form.fullName}
              autoComplete="name"
              onChange={(fullName) => setForm((previous) => ({ ...previous, fullName }))}
              error={submitted ? errorFor("fullName") : undefined}
            />
          )}

          <Field
            label="Email address"
            type="email"
            placeholder="you@example.com"
            value={form.email}
            autoComplete="email"
            onChange={(email) => setForm((previous) => ({ ...previous, email }))}
            error={submitted ? errorFor("email") : undefined}
          />

          <Field
            label="Password"
            type="password"
            placeholder={isRegister ? "At least 8 characters" : "Your password"}
            value={form.password}
            autoComplete={isRegister ? "new-password" : "current-password"}
            onChange={(password) => setForm((previous) => ({ ...previous, password }))}
            error={submitted ? errorFor("password") : undefined}
          />

          {isRegister && (
            <Field
              label="Confirm password"
              type="password"
              placeholder="Repeat your password"
              value={form.passwordConfirm}
              autoComplete="new-password"
              onChange={(passwordConfirm) => setForm((previous) => ({ ...previous, passwordConfirm }))}
              error={submitted ? errorFor("passwordConfirm") : undefined}
            />
          )}

          {isRegister ? (
            <label className="terms-row">
              <input
                type="checkbox"
                checked={form.acceptedTerms}
                onChange={(event) =>
                  setForm((previous) => ({ ...previous, acceptedTerms: event.target.checked }))
                }
              />
              <span>
                I agree to the Terms of Service and Privacy Policy.
                {submitted && errorFor("acceptedTerms") && (
                  <small className="error">{errorFor("acceptedTerms")}</small>
                )}
              </span>
            </label>
          ) : (
            <div className="form-meta">
              <label>
                <input
                  type="checkbox"
                  checked={form.remember}
                  onChange={(event) =>
                    setForm((previous) => ({ ...previous, remember: event.target.checked }))
                  }
                />{" "}
                Remember me
              </label>
              <a href="#forgot" onClick={(event) => event.preventDefault()}>
                Forgot password?
              </a>
            </div>
          )}

          <Button type="submit" className="wide" disabled={submitting}>
            {submitting ? "Please wait…" : isRegister ? "Create account" : "Log in"}
          </Button>

          <div className="switch-auth">
            {isRegister ? "Already have an account?" : "New to SmartCover?"}{" "}
            <button type="button" onClick={() => navigate(isRegister ? "/login" : "/register")}>
              {isRegister ? "Log in" : "Create account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
