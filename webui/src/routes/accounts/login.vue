<script lang="ts">
import { useMutation } from "@pinia/colada"
import { useRegle, type RegleExternalErrorTree } from "@regle/core"
import { required } from "@regle/rules"
import { useCookies } from "@vueuse/integrations/useCookies"
import { mande, type MandeError } from "mande"
import { useSelfStore, type Payload } from "~/stores/self"

type Credentials = {
  username: string
  password: string
}
</script>

<script lang="ts" setup>
import { Button, Card, CardContent, CardHeader, Field, FieldError, FieldGroup, FieldLabel, Input } from "~/shadcn"

const cookies = useCookies(["csrftoken"])
const router = useRouter()
const selfStore = useSelfStore()

const { r$: form } = useRegle(
  <Credentials>{
    username: "",
    password: "",
  },
  {
    username: { required },
    password: { required },
  },
  {
    externalErrors: ref<RegleExternalErrorTree<Credentials>>({}),
  },
)
const formNonFieldErrors = ref<string[] | null>()

const login = useMutation({
  mutation(data: Credentials) {
    return mande("/email/api/v1/self").post<Payload, "json">("login", data, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(error: MandeError) {
    const { non_field_errors, username, password } = error.body
    formNonFieldErrors.value = non_field_errors
    form.$setExternalErrors({ username, password })
  },
  onSuccess: async (payload_value) => {
    formNonFieldErrors.value = null
    await selfStore.initialize(payload_value)
    if (selfStore.userIsAgent) {
      router.push({ name: "workspace" })
    } else {
      window.location.href = "/"
    }
  },
})

async function handleSubmit() {
  const { valid, data } = await form.$validate()
  if (valid) {
    login.mutate(data)
  }
}
</script>

<template lang="html">
  <div class="bg-muted flex min-h-svh flex-col items-center justify-center gap-6 p-6">
    <div class="flex w-full max-w-sm flex-col gap-6">
      <Card>
        <CardHeader>
          <img class="mx-auto" v-bind:src="selfStore.brandLogoFull" alt="" />
        </CardHeader>
        <CardContent>
          <form id="form" v-on:submit.prevent.stop="handleSubmit">
            <FieldGroup>
              <Field v-bind:data-invalid="form.username.$error">
                <FieldLabel for="username">
                  {{ "Username" }}
                </FieldLabel>
                <Input
                  autocomplete="username"
                  id="username"
                  type="text"
                  v-bind:aria-invalid="form.username.$error"
                  v-model="form.username.$value" />
                <FieldError class="text-xs" v-if="form.username.$error" v-bind:errors="form.username.$errors" />
              </Field>
              <Field v-bind:data-invalid="form.password.$error">
                <FieldLabel for="password">
                  {{ "Password" }}
                </FieldLabel>
                <Input
                  autocomplete="current-password"
                  id="password"
                  type="password"
                  v-bind:aria-invalid="form.password.$error"
                  v-model="form.password.$value" />
                <FieldError class="text-xs" v-if="form.password.$error" v-bind:errors="form.password.$errors" />
              </Field>
              <Button type="submit">
                {{ "Login" }}
              </Button>
              <FieldError class="text-sm" v-if="formNonFieldErrors" v-bind:errors="formNonFieldErrors" />
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
