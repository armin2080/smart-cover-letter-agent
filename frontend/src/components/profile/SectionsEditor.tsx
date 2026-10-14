import { useState } from "react"
import { Button } from "../ui/Button"
import { Icon } from "../ui/Icon"
import type { ProfileSection } from "../../types"

interface SectionsEditorProps {
  sections: ProfileSection[]
  onSave: (sectionId: string, content: string) => Promise<void>
  /** Sections the user may edit. Defaults to all. */
  editable?: boolean
}

/**
 * Structured, independently editable CV sections.
 *
 * Shared by onboarding (profile review) and the profile page so both stay
 * consistent and only one implementation needs maintaining.
 */
export function SectionsEditor({ sections, onSave, editable = true }: SectionsEditorProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [savingId, setSavingId] = useState<string | null>(null)

  const startEdit = (section: ProfileSection) => {
    setEditingId(section.id)
    setDraft(section.content)
  }

  const save = async (section: ProfileSection) => {
    setSavingId(section.id)
    try {
      await onSave(section.id, draft)
      setEditingId(null)
    } finally {
      setSavingId(null)
    }
  }

  return (
    <>
      {sections.map((section) => {
        const isEditing = editingId === section.id
        return (
          <section className="editable-section" key={section.id}>
            <div>
              <h3>{section.title}</h3>
              {isEditing ? (
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  aria-label={`Edit ${section.title}`}
                  rows={4}
                />
              ) : (
                section.content.split("\n").map((line, index) => <p key={index}>{line}</p>)
              )}
            </div>

            {editable &&
              (isEditing ? (
                <div className="section-actions">
                  <Button kind="ghost" onClick={() => setEditingId(null)}>
                    Cancel
                  </Button>
                  <Button onClick={() => save(section)} disabled={savingId === section.id}>
                    {savingId === section.id ? "Saving…" : "Save"}
                  </Button>
                </div>
              ) : (
                <button
                  className="section-edit"
                  type="button"
                  onClick={() => startEdit(section)}
                  aria-label={`Edit ${section.title}`}
                >
                  <Icon name="edit" size={14} /> Edit
                </button>
              ))}
          </section>
        )
      })}
    </>
  )
}
