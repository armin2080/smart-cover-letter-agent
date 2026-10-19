import { EMPLOYMENT_OPTIONS, LANGUAGE_FILTER_OPTIONS, SOURCE_OPTIONS } from "../../lib/labels"
import { TagInput } from "../ui/TagInput"
import type { Preferences } from "../../types"

interface PreferencesFormProps {
  value: Preferences
  onChange: (next: Preferences) => void
  disabled?: boolean
}

const toggled = <T,>(list: T[], entry: T): T[] =>
  list.includes(entry) ? list.filter((item) => item !== entry) : [...list, entry]

/**
 * Job-preference form shared by onboarding, the profile page and settings.
 *
 * Preferences are deliberately separate from the CV-derived qualifications:
 * they describe intent, while the CV describes experience.
 */
export function PreferencesForm({ value, onChange, disabled = false }: PreferencesFormProps) {
  const patch = (changes: Partial<Preferences>) => onChange({ ...value, ...changes })

  return (
    <div className="preferences-form">
      <label className="field">
        <span>Desired job titles</span>
        <TagInput
          value={value.desiredRoles}
          onChange={(desiredRoles) => patch({ desiredRoles })}
          placeholder="Add a job title and press Enter"
          ariaLabel="Desired job titles"
          disabled={disabled}
        />
      </label>

      <label className="field">
        <span>Preferred locations</span>
        <TagInput
          value={value.locations}
          onChange={(locations) => patch({ locations })}
          placeholder="Add a location and press Enter"
          ariaLabel="Preferred locations"
          disabled={disabled}
        />
      </label>

      <div className="field">
        <span>Search radius</span>
        <div className="range-field">
          <input
            type="range"
            min={0}
            max={150}
            step={5}
            value={value.radiusKm}
            disabled={disabled}
            aria-label="Search radius in kilometres"
            onChange={(event) => patch({ radiusKm: Number(event.target.value) })}
          />
          <b>{value.radiusKm} km</b>
        </div>
      </div>

      <div className="field">
        <span>Employment types</span>
        <div className="check-grid">
          {EMPLOYMENT_OPTIONS.map((option) => (
            <label className="check-item" key={option.value}>
              <input
                type="checkbox"
                checked={value.employmentTypes.includes(option.value)}
                disabled={disabled}
                onChange={() => patch({ employmentTypes: toggled(value.employmentTypes, option.value) })}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="field">
        <span>Preferred sources</span>
        <div className="check-grid">
          {SOURCE_OPTIONS.map((source) => (
            <label className="check-item" key={source}>
              <input
                type="checkbox"
                checked={value.sources.includes(source)}
                disabled={disabled}
                onChange={() => patch({ sources: toggled(value.sources, source) })}
              />
              <span>{source}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="field">
        <span>Posting language</span>
        <div className="check-grid">
          {LANGUAGE_FILTER_OPTIONS.map((option) => (
            <label className="check-item" key={option.value}>
              <input
                type="radio"
                name="language-filter"
                checked={value.languageFilter === option.value}
                disabled={disabled}
                onChange={() => patch({ languageFilter: option.value })}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
        <small className="hint">
          Many postings on German boards are written in German. Choosing one language hides the others, and
          listings whose language could not be determined.
        </small>
      </div>

      <label className="field">
        <span>Relevant keywords</span>
        <TagInput
          value={value.keywords}
          onChange={(keywords) => patch({ keywords })}
          placeholder="Add a keyword and press Enter"
          ariaLabel="Relevant keywords"
          disabled={disabled}
        />
        <small className="hint">Used to broaden matches beyond exact job titles.</small>
      </label>
    </div>
  )
}
