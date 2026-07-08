import { PiniaColada, PiniaColadaQueryHooksPlugin } from "@pinia/colada"
import { PiniaColadaDelay } from "@pinia/colada-plugin-delay"
import { PiniaColadaRetry } from "@pinia/colada-plugin-retry"
import { RegleVuePlugin, defineRegleOptions } from "@regle/core"
import { createPinia } from "pinia"
import { default as PiniaPersistedState } from "pinia-plugin-persistedstate"
import { default as qs } from "qs"
import { createRouter, createWebHistory } from "vue-router"
import { default as App } from "~/app.vue"
import { equalizeChildrenWidthDirective, equalizeIframeHeight } from "~/directives"
import { beforeResolve, routes } from "~/routes"

const pinia = createPinia()

pinia.use(PiniaPersistedState)

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  parseQuery: (search) => {
    return qs.parse(search, { ignoreQueryPrefix: true, strictNullHandling: true }) as any
  },
  routes,
  scrollBehavior(to, from, position) {
    return position ?? { top: 0 }
  },
  stringifyQuery: (query) => {
    return qs.stringify(query, { encodeValuesOnly: true, strictNullHandling: true })
  },
})

router.beforeResolve(beforeResolve)

const app = createApp(App, {})

app.directive("equalize-children-width", equalizeChildrenWidthDirective)

app.directive("equalize-iframe-height", equalizeIframeHeight)

app.use(pinia)

app.use(PiniaColada, {
  queryOptions: {},
  mutationOptions: {},
  plugins: [
    PiniaColadaDelay({ delay: 30 }),
    PiniaColadaQueryHooksPlugin({}),
    PiniaColadaRetry({ retry: 3 }),
  ],
})

app.use(RegleVuePlugin, defineRegleOptions({}))

app.use(router)

app.mount("#app")
