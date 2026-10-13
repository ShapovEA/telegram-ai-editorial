const ALLOWED = new Set(["B", "STRONG", "I", "EM", "U", "INS", "S", "STRIKE", "DEL", "A", "CODE", "PRE", "BLOCKQUOTE", "BR", "TG-SPOILER", "SPAN"])

function clean(node: Node, doc: Document): Node | null {
  if (node.nodeType === Node.TEXT_NODE) return doc.createTextNode(node.textContent ?? "")
  if (node.nodeType !== Node.ELEMENT_NODE) return null
  const el = node as Element
  const children = [...el.childNodes].map((c) => clean(c, doc)).filter((c): c is Node => c !== null)
  if (!ALLOWED.has(el.tagName)) {
    const frag = doc.createDocumentFragment()
    children.forEach((c) => frag.appendChild(c))
    return frag
  }
  const out = doc.createElement(el.tagName === "TG-SPOILER" ? "span" : el.tagName.toLowerCase())
  if (el.tagName === "A") {
    const href = el.getAttribute("href") ?? ""
    if (/^https?:\/\//i.test(href)) {
      out.setAttribute("href", href)
      out.setAttribute("target", "_blank")
      out.setAttribute("rel", "noreferrer noopener")
    }
  }
  if (el.tagName === "TG-SPOILER" || (el.tagName === "SPAN" && el.classList.contains("tg-spoiler"))) out.setAttribute("class", "tg-spoiler")
  if (el.tagName === "BLOCKQUOTE" && el.hasAttribute("expandable")) out.setAttribute("data-expandable", "")
  children.forEach((c) => out.appendChild(c))
  return out
}

export function sanitizeTelegramHtml(html: string): string {
  const doc = new DOMParser().parseFromString(`<body>${html.replace(/\n/g, "<br>")}</body>`, "text/html")
  const root = document.createElement("div")
  for (const child of [...doc.body.childNodes]) {
    const c = clean(child, document)
    if (c) root.appendChild(c)
  }
  return root.innerHTML
}
