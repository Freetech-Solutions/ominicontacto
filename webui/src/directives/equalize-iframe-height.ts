import type { Directive } from "vue"

function apply(this: HTMLIFrameElement) {
  if (this.contentWindow) {
    const height = Math.max(
      this.contentWindow.document.body.scrollHeight,
      this.contentWindow.document.documentElement.scrollHeight,
    )
    this.style.setProperty("height", `${height}px`)
  }
}

export default <Directive>{
  mounted(el: HTMLIFrameElement) {
    if (el.tagName !== "IFRAME") {
      console.warn("v-equalize-iframe-height requires IFRAME")
      return
    }
    el.addEventListener("load", apply)
  },
  unmounted(el) {
    el.removeEventListener("load", apply)
  },
}
