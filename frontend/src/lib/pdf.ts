/**
 * Minimal, dependency-free PDF writer.
 *
 * Produces a valid single/multi-page PDF for plain-text documents so the mock
 * transport can return a genuinely downloadable file. When the Django backend
 * is live, PDFs are rendered server-side (ReportLab) and this module is only
 * used as an offline fallback.
 */

const PAGE_WIDTH = 595.28 // A4 @ 72dpi
const PAGE_HEIGHT = 841.89
const MARGIN_X = 56
const MARGIN_TOP = 786
const MARGIN_BOTTOM = 56
const FONT_SIZE = 11
const LINE_HEIGHT = 15
const MAX_CHARS = 92

/** Escape characters that are special inside a PDF literal string. */
function escapeText(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)")
}

/** Greedy word wrap that also preserves explicit newlines and blank lines. */
function wrapText(text: string): string[] {
  const output: string[] = []

  for (const rawLine of text.split(/\r?\n/)) {
    if (!rawLine.trim()) {
      output.push("")
      continue
    }

    let current = ""
    for (const word of rawLine.split(/\s+/)) {
      if (!current) {
        current = word
      } else if (`${current} ${word}`.length <= MAX_CHARS) {
        current = `${current} ${word}`
      } else {
        output.push(current)
        current = word
      }
    }
    if (current) output.push(current)
  }

  return output
}

function paginate(lines: string[]): string[][] {
  const perPage = Math.floor((MARGIN_TOP - MARGIN_BOTTOM) / LINE_HEIGHT)
  const pages: string[][] = []
  for (let index = 0; index < lines.length; index += perPage) {
    pages.push(lines.slice(index, index + perPage))
  }
  return pages.length ? pages : [[""]]
}

function buildContentStream(lines: string[]): string {
  const commands = ["BT", `/F1 ${FONT_SIZE} Tf`, `${LINE_HEIGHT} TL`, `${MARGIN_X} ${MARGIN_TOP} Td`]
  lines.forEach((line, index) => {
    if (index > 0) commands.push("T*")
    if (line) commands.push(`(${escapeText(line)}) Tj`)
  })
  commands.push("ET")
  return commands.join("\n")
}

/** Compose a PDF and return it as a Blob. */
export function createTextPdf(title: string, body: string): Blob {
  const lines = wrapText(body)
  const pages = paginate(lines)
  const pageCount = pages.length

  // Object layout: 1 catalog, 2 pages tree, 3 font, then 4+ page/content pairs.
  const fontObjectNumber = 3
  const firstPageObjectNumber = 4

  const objects: string[] = []
  const pageRefs: number[] = []

  pages.forEach((_, index) => {
    pageRefs.push(firstPageObjectNumber + index * 2)
  })

  objects.push(`<< /Type /Catalog /Pages 2 0 R >>`)
  objects.push(
    `<< /Type /Pages /Kids [${pageRefs.map((ref) => `${ref} 0 R`).join(" ")}] /Count ${pageCount} >>`,
  )
  objects.push(`<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>`)

  pages.forEach((pageLines, index) => {
    const contentObjectNumber = firstPageObjectNumber + index * 2 + 1
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH.toFixed(2)} ${PAGE_HEIGHT.toFixed(2)}] ` +
        `/Resources << /Font << /F1 ${fontObjectNumber} 0 R >> >> /Contents ${contentObjectNumber} 0 R >>`,
    )

    const header = index === 0 ? [title, ""] : []
    const stream = buildContentStream([...header, ...pageLines])
    objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`)
  })

  let pdf = "%PDF-1.4\n"
  const offsets: number[] = []

  objects.forEach((object, index) => {
    offsets.push(pdf.length)
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`
  })

  const xrefOffset = pdf.length
  pdf += `xref\n0 ${objects.length + 1}\n`
  pdf += `0000000000 65535 f \n`
  for (const offset of offsets) {
    pdf += `${offset.toString().padStart(10, "0")} 00000 n \n`
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`

  // Latin-1 keeps the byte length aligned with the string length used in /Length.
  const bytes = new Uint8Array(pdf.length)
  for (let index = 0; index < pdf.length; index += 1) {
    bytes[index] = pdf.charCodeAt(index) & 0xff
  }
  return new Blob([bytes], { type: "application/pdf" })
}

/** Build a filename safe for download. */
export function coverLetterFileName(company: string, jobTitle: string): string {
  const slug = `${company}-${jobTitle}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
  return `cover-letter-${slug}.pdf`
}
