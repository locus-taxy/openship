import DOMPurify from "dompurify"

/**
 * Sanitize HTML from Gemini newsletter output before rendering with
 * dangerouslySetInnerHTML. Strips scripts, event handlers, and dangerous
 * URLs (javascript:, data:) while keeping safe formatting tags.
 */
export function sanitizeHtml(raw: string | null | undefined): string {
    if (!raw) return ""
    try {
        return DOMPurify.sanitize(raw, {
            ALLOWED_TAGS: [
                "h1", "h2", "h3", "h4", "h5", "h6",
                "p", "br", "hr",
                "ul", "ol", "li",
                "strong", "b", "em", "i", "u", "s", "code", "pre",
                "blockquote",
                "a",
                "table", "thead", "tbody", "tr", "th", "td",
                "div", "span",
            ],
            ALLOWED_ATTR: ["href", "title", "target", "rel", "scope", "colspan", "rowspan"],
            ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
            FORCE_BODY: true,
        })
    } catch {
        return ""
    }
}
