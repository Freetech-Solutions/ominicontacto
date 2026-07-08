import { mande } from "mande"
import { defineStore } from "pinia"

export type Payload = {
  brand: {
    logo_full: string
  }
  user:
    | {
        id: null
        is_anonymous: true
        is_authenticated: false
        is_agent: false
        is_supervisor: false
      }
    | {
        id: number
        username: string
        first_name: string
        last_name: string
        is_anonymous: false
        is_authenticated: true
        is_agent: boolean
        is_supervisor: boolean
      }
}

export const useSelfStore = defineStore("self", () => {
  const payload = ref<Payload>()

  const initialized = computed(() => payload.value !== undefined)
  const brandLogoFull = computed(() => payload.value?.brand.logo_full)
  const userIsAgent = computed(() => payload.value?.user.is_agent)
  const userIsAnonymous = computed(() => payload.value?.user.is_anonymous)

  async function initialize(payload_value?: Payload) {
    payload.value = payload_value ?? (await mande("/email/api/v1/self").get("payload"))
  }

  return {
    payload,
    initialized,
    brandLogoFull,
    userIsAgent,
    userIsAnonymous,
    initialize,
  }
})
