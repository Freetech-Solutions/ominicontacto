import type { Directive } from "vue"

function apply(el: HTMLElement) {
  const children = Array.from(el.children) as HTMLElement[]
  const maxwidth = Math.max(
    ...children.map((child) => Math.ceil(child.getBoundingClientRect().width)),
  )

  children.forEach((child) => {
    child.style.setProperty("min-width", `${maxwidth + 8}px`)
  })
}

export default <Directive>{
  mounted(el) {
    apply(el)
  },
}
