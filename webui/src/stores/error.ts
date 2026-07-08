import { defineStore } from "pinia"

type Error = {
  id: string
  code: number
  name: string
  details: string
  timestamp: number
}

export const useErrorsStore = defineStore(
  "error",
  function () {
    const errors = ref<Record<string, Error>>({})

    function append(data: Omit<Error, "id" | "timestamp">) {
      const error = <Error>{ ...data, id: crypto.randomUUID(), timestamp: Date.now() }
      errors.value[error.id] = error
      return error.id
    }

    function clear() {
      errors.value = {}
    }

    function get(id: string) {
      return errors.value[id]
    }

    function remove(id: string) {
      delete errors.value[id]
    }

    return { append, clear, errors, get, remove }
  },
  {
    persist: {
      key: "pinia-persisted-state:error",
      storage: sessionStorage,
    },
  },
)
