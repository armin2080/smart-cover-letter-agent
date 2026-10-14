import { useState, type KeyboardEvent } from "react"
import { Icon } from "./Icon"

interface TagInputProps {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  ariaLabel?: string
  disabled?: boolean
}

/** Chip-style input for lists of short strings (roles, locations, keywords). */
export function TagInput({ value, onChange, placeholder, ariaLabel, disabled = false }: TagInputProps) {
  const [draft, setDraft] = useState("")

  const commit = () => {
    const entry = draft.trim()
    if (!entry) return
    if (!value.includes(entry)) onChange([...value, entry])
    setDraft("")
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault()
      commit()
      return
    }
    if (event.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className="chip-field">
      {value.map((entry) => (
        <span className="chip" key={entry}>
          {entry}
          <button
            type="button"
            disabled={disabled}
            aria-label={`Remove ${entry}`}
            onClick={() => onChange(value.filter((item) => item !== entry))}
          >
            <Icon name="close" size={11} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        disabled={disabled}
        placeholder={value.length ? "" : placeholder}
        aria-label={ariaLabel}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commit}
      />
    </div>
  )
}
