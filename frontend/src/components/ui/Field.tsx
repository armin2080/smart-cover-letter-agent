interface FieldProps {
  label: string
  placeholder?: string
  type?: string
  value?: string
  onChange?: (value: string) => void
  error?: string
  hint?: string
  autoComplete?: string
  disabled?: boolean
  required?: boolean
  inputMode?: "text" | "numeric" | "decimal" | "email" | "tel" | "url" | "search"
  min?: string | number
  max?: string | number
  step?: string | number
}

export function Field({
  label,
  placeholder,
  type = "text",
  value,
  onChange,
  error,
  hint,
  autoComplete,
  disabled = false,
  required = false,
  inputMode,
  min,
  max,
  step,
}: FieldProps) {
  return (
    <label className="field">
      <span>
        {label}
        {required && " *"}
      </span>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        autoComplete={autoComplete}
        disabled={disabled}
        required={required}
        inputMode={inputMode}
        min={min}
        max={max}
        step={step}
        aria-invalid={error ? true : undefined}
      />
      {hint && !error && <small className="hint">{hint}</small>}
      {error && <small className="error">{error}</small>}
    </label>
  )
}

