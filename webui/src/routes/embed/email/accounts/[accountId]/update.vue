<script lang="ts">
import { useMutation, useQuery, useQueryCache } from "@pinia/colada"
import { useRegle, type RegleExternalErrorTree } from "@regle/core"
import { boolean, maxLength, maxValue, minValue, number, required, string } from "@regle/rules"
import { useCookies } from "@vueuse/integrations/useCookies"
import { mande, type MandeError } from "mande"
import { toast } from "vue-sonner"
import { iso8601dateString } from "~/rules/iso8601dateString"

export type Account = {
  id: number
  name: string
  active: boolean
  inbound: {
    protocol: string
    host: string
    port: number
    auth_type: string
    username: string
    password: string
    fetch_mode: string
    idle_duration: number
    poll_interval: number
    mailbox: string
    since: string
    ssl_check_hostname: boolean
  }
  outbound: {
    protocol: string
    host: string
    port: number
    auth_type: string
    username: string
    password: string
    from_addr: string
    from_name: string
    include_agent_name: boolean
    signature_text: string
    signature_image: string
  }
}
</script>

<script lang="ts" setup>
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  AlertTitle,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
  Input,
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  Popover,
  PopoverContent,
  PopoverTrigger,
  ScrollArea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Switch,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "~/shadcn"

const { accountId } = defineProps<{ accountId: number }>()

const api = mande("/email/api/v1/accounts")
const cache = useQueryCache()
const cookies = useCookies(["csrftoken"])
const router = useRouter()

const form = ref<Account>({
  id: 0,
  name: "",
  active: true,
  inbound: {
    protocol: "",
    host: "",
    port: 0,
    auth_type: "",
    username: "",
    password: "",
    fetch_mode: "",
    idle_duration: 0,
    poll_interval: 0,
    mailbox: "",
    since: "",
    ssl_check_hostname: true,
  },
  outbound: {
    protocol: "",
    host: "",
    port: 0,
    auth_type: "",
    username: "",
    password: "",
    from_addr: "",
    from_name: "",
    include_agent_name: false,
    signature_text: "",
    signature_image: "",
  },
})

const { r$ } = useRegle(
  form,
  {
    id: { required, number },
    name: { required, maxLength: maxLength(100) },
    active: { required, boolean },
    inbound: {
      protocol: { required },
      host: { required },
      port: { required, number, minValue: minValue(0), maxValue: maxValue(65535) },
      auth_type: { required },
      username: { required },
      password: { string },
      fetch_mode: { required },
      idle_duration: { required, number, minValue: minValue(180), maxValue: maxValue(1740) },
      poll_interval: { required, number, minValue: minValue(180), maxValue: maxValue(86400) },
      mailbox: { required },
      since: { iso8601dateString },
      ssl_check_hostname: { required, boolean },
    },
    outbound: {
      protocol: { required },
      host: { required },
      port: { required, number, minValue: minValue(0), maxValue: maxValue(65535) },
      auth_type: { required },
      username: { required },
      password: { string },
      from_addr: { required },
      from_name: { maxLength: maxLength(100) },
      include_agent_name: { boolean },
      signature_text: { maxLength: maxLength(4000) },
      signature_image: {},
    },
  },
  {
    id: `account:${accountId}`,
    externalErrors: ref<RegleExternalErrorTree<Account>>({}),
  },
)

const retrieve = useQuery<Account, MandeError<any>, undefined>({
  key: () => ["email-accounts", accountId],
  query() {
    return api.get<Account>(accountId)
  },
})

watch(
  retrieve.data,
  async (data) => {
    if (data && !r$.$anyEdited) {
      form.value = data
      await nextTick()
      r$.$reset()
    }
  },
  {
    immediate: true,
  },
)

const create = useMutation({
  mutation({ id, ...data }: Account) {
    return api.post<Pick<Account, "id">, "json">(`${id}/template`, data, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(error: MandeError) {
    r$.$setExternalErrors(error.body)
  },
  onSuccess: async ({ id }) => {
    toast.success("Account created", { description: "Account has been successfully created" })
    r$.$reset()
    await router.push({ name: "embed:email:account:update", params: { accountId: id } })
  },
})

const destroy = useMutation({
  mutation(id: number) {
    return api.delete<undefined>(id, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(error: MandeError) {
    toast.error(error.body?.detail ?? error.toString())
  },
  onSuccess: async () => {
    toast.success("Account deleted", { description: "Associated data has been removed" })
    await router.push({ name: "embed:email:account:list" })
  },
})

const update = useMutation({
  mutation({ id, ...data }: Account) {
    return api.put<Account, "json">(id, data, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(error: MandeError) {
    r$.$setExternalErrors(error.body)
  },
  onSuccess: async () => {
    toast.success("Account updated", { description: "Your changes have been saved" })
    await router.push({ name: "embed:email:account:list" })
  },
})

const updatePartial = useMutation({
  mutation({ id, ...data }: Account) {
    return api.put<Account, "json">(id, data, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(error: MandeError) {
    r$.$setExternalErrors(error.body)
  },
  onSuccess: async (data) => {
    toast.success("Account updated", { description: "Your changes have been saved" })
    form.value = data
    await nextTick()
    r$.$reset()
  },
})

const testTo = ref("")
const test = useMutation({
  mutation({ id, to }: { id: number; to: string }) {
    return api.post<{ outbound?: { ok: boolean; errors?: string[] } }, "json">(
      `${id}/test`,
      { action: ["outbound"], to },
      { headers: { "x-csrftoken": cookies.get("csrftoken") } },
    )
  },
  onError(error: MandeError) {
    toast.error("No se pudo ejecutar el test", {
      description: error.body?.detail ?? error.toString(),
    })
  },
  onSuccess(data) {
    const result = data?.outbound
    if (result?.ok) {
      toast.success("Test de envío OK", {
        description: "El correo de prueba se envió correctamente.",
      })
    } else {
      toast.error("Falló el test de envío", {
        description: (result?.errors ?? []).join(" ") || "Revisá la configuración SMTP.",
      })
    }
  },
})

function onSignatureImage(event: Event, model: { $value: string }) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    model.$value = reader.result as string
  }
  reader.readAsDataURL(file) // -> data:image/png;base64,....
}

function handleTest() {
  if (!testTo.value) return
  test.mutate({ id: accountId, to: testTo.value })
}

function handleRefetch() {
  if (!retrieve.isLoading.value) {
    retrieve.refetch(true)
  }
}

function handleDestroy() {
  destroy.mutate(accountId)
}

async function handleSubmit({ submitter }: SubmitEvent) {
  const { valid, data } = await r$.$validate()
  if (valid && submitter) {
    const action = (submitter as HTMLButtonElement).value
    if (action === "create") {
      create.mutate(data as Account)
    } else if (action === "update-partial") {
      updatePartial.mutate(data as Account)
    } else if (action === "update") {
      update.mutate(data as Account)
    }
  }
}
</script>

<template lang="html">
  <Card>
    <div class="grid grid-cols-[auto_1fr] gap-2 px-6">
      <Button class="rounded-full" size="icon-lg" variant="secondary" as-child>
        <router-link v-bind:to="{ name: 'embed:email:account:list' }">
          <i-hugeicons-arrow-left-01 class="size-8" />
        </router-link>
      </Button>
      <CardHeader class="px-0">
        <CardTitle>
          {{ "Email Account" }}
        </CardTitle>
        <CardDescription>
          {{ "Make changes to the email account here" }}
        </CardDescription>
        <CardAction class="flex gap-2">
          <Popover>
            <PopoverTrigger as-child>
              <Button variant="outline">
                {{ "Test de envío" }}
              </Button>
            </PopoverTrigger>
            <PopoverContent class="w-80 flex flex-col gap-2">
              <FieldLabel for="test-to">
                {{ "Enviar correo de prueba a" }}
              </FieldLabel>
              <Input
                id="test-to"
                type="email"
                placeholder="tu@correo.com"
                v-model="testTo"
                v-on:keydown.enter.prevent="handleTest" />
              <FieldDescription class="text-xs">
                {{ "Recibís el test fuera del servidor para confirmar la entrega." }}
              </FieldDescription>
              <Button
                class="self-end"
                v-bind:disabled="test.isLoading.value || !testTo"
                v-on:click="handleTest">
                {{ test.isLoading.value ? "Enviando…" : "Enviar prueba" }}
              </Button>
            </PopoverContent>
          </Popover>
          <Button size="icon-lg" variant="outline" v-on:click="handleRefetch">
            <i-hugeicons-repost class="size-6" />
          </Button>
          <AlertDialog>
            <AlertDialogTrigger as-child>
              <Button size="icon-lg" variant="outline">
                <i-hugeicons-delete-02 class="size-6" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {{ "Are you sure?" }}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {{ "You want to delete this account?" }}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter v-equalize-children-width>
                <AlertDialogCancel>
                  {{ "Cancel" }}
                </AlertDialogCancel>
                <AlertDialogAction variant="destructive" v-on:click="handleDestroy">
                  {{ "Delete" }}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Tooltip>
            <TooltipTrigger>
              <Button size="icon-lg" type="submit" variant="outline" form="form" value="create">
                <i-hugeicons-save-all class="size-6" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {{ "Create a new account using this one as a template" }}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger>
              <Button size="icon-lg" type="submit" variant="outline" form="form" value="update" class="relative">
                <i-hugeicons-save class="absolute bottom-1 left-1 size-6" />
                <i-hugeicons-arrow-move-up-left class="absolute top-[1px] right-0 size-6" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {{ "Save and finish editing" }}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger>
              <Button size="icon-lg" type="submit" variant="outline" form="form" value="update-partial">
                <i-hugeicons-save class="size-6" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {{ "Save and continue editing" }}
            </TooltipContent>
          </Tooltip>
        </CardAction>
      </CardHeader>
    </div>
    <CardContent>
      <template v-if="retrieve.status.value === 'error'">
        <Alert variant="destructive">
          <i-hugeicons-alert-circle class="size-6" />
          <AlertTitle>
            {{ "Unable to retrieve account" }}
          </AlertTitle>
          <AlertDescription v-if="retrieve.error.value">
            <p>{{ retrieve.error.value.body?.detail || retrieve.error.value.toString() }}</p>
          </AlertDescription>
        </Alert>
      </template>
      <template v-else>
        <ScrollArea class="-mx-4 max-h-[calc(100vh-150px)] overflow-auto">
          <form id="form" v-on:submit.prevent.stop="handleSubmit($event)">
            <FieldGroup class="px-4">
              <Field v-bind:data-invalid="r$.name.$error">
                <FieldLabel for="name">
                  {{ "Name" }}
                </FieldLabel>
                <InputGroup>
                  <InputGroupInput id="name" type="text" v-bind:aria-invalid="r$.name.$error" v-model="r$.name.$value" />
                  <InputGroupAddon align="inline-end" class="text-xs" v-if="r$.name.$value">
                    {{ r$.name.$value?.length }}/{{ r$.name.$rules.maxLength.$params[0] }}
                  </InputGroupAddon>
                </InputGroup>
                <FieldError class="text-xs" v-if="r$.name.$error" v-bind:errors="r$.name.$errors" />
              </Field>
              <Field orientation="horizontal" v-bind:data-invalid="r$.active.$error">
                <Switch id="active" v-bind:aria-invalid="r$.active.$error" v-model="r$.active.$value" />
                <FieldContent>
                  <FieldLabel for="active">
                    {{ "Active" }}
                  </FieldLabel>
                  <FieldDescription>
                    {{ "You can deactivate the account to prevent further interactions" }}
                  </FieldDescription>
                  <FieldError class="text-xs" v-if="r$.active.$error" v-bind:errors="r$.active.$errors" />
                </FieldContent>
              </Field>
              <FieldSeparator />
              <div class="grid gap-6 lg:grid-cols-[1fr_auto_1fr]">
                <FieldSet>
                  <FieldLegend class="text-center">
                    {{ "Incoming Mail Server" }}
                  </FieldLegend>
                  <FieldDescription class="text-center">
                    {{ "from where the messages will be received" }}
                  </FieldDescription>
                  <FieldSeparator class="hidden lg:block" />
                  <FieldGroup>
                    <div class="grid gap-6 lg:grid-cols-4">
                      <Field v-bind:data-invalid="r$.inbound.protocol.$error">
                        <FieldLabel for="inbound.protocol">
                          {{ "Protocol" }}
                        </FieldLabel>
                        <Select id="inbound.protocol" v-bind:aria-invalid="r$.inbound.protocol.$error" v-model="r$.inbound.protocol.$value">
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="imap" disabled>IMAP</SelectItem>
                            <SelectItem value="imap+tls" disabled>IMAP with TLS</SelectItem>
                            <SelectItem value="imap+ssl">IMAP with SSL</SelectItem>
                          </SelectContent>
                        </Select>
                        <FieldError class="text-xs" v-if="r$.inbound.protocol.$error" v-bind:errors="r$.inbound.protocol.$errors" />
                      </Field>
                      <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                        <Field class="lg:col-span-3" v-bind:data-invalid="r$.inbound.host.$error">
                          <FieldLabel for="inbound.host">
                            {{ "Host" }}
                          </FieldLabel>
                          <Input
                            id="inbound.host"
                            type="text"
                            v-bind:aria-invalid="r$.inbound.host.$error"
                            v-model="r$.inbound.host.$value" />
                          <FieldError class="text-xs" v-if="r$.inbound.host.$error" v-bind:errors="r$.inbound.host.$errors" />
                        </Field>
                        <Field v-bind:data-invalid="r$.inbound.port.$error">
                          <FieldLabel for="inbound.port">
                            {{ "Port" }}
                          </FieldLabel>
                          <Input
                            id="inbound.port"
                            type="number"
                            v-bind:aria-invalid="r$.inbound.port.$error"
                            v-bind:mix="r$.inbound.port.$rules.minValue.$params[0]"
                            v-bind:max="r$.inbound.port.$rules.maxValue.$params[0]"
                            v-model="r$.inbound.port.$value" />
                          <FieldError class="text-xs" v-if="r$.inbound.port.$error" v-bind:errors="r$.inbound.port.$errors" />
                        </Field>
                      </div>
                    </div>
                    <div class="grid gap-6 lg:grid-cols-4">
                      <Field v-bind:data-invalid="r$.inbound.auth_type.$error">
                        <FieldLabel for="inbound.auth_type">
                          {{ "Auth type" }}
                        </FieldLabel>
                        <Select
                          id="inbound.auth_type"
                          v-bind:aria-invalid="r$.inbound.auth_type.$error"
                          v-model="r$.inbound.auth_type.$value">
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="basic">BASIC</SelectItem>
                          </SelectContent>
                        </Select>
                        <FieldDescription class="text-xs">
                          {{ "For Gmail / Google Workspace use BASIC with an App Password." }}
                        </FieldDescription>
                        <FieldError class="text-xs" v-if="r$.inbound.auth_type.$error" v-bind:errors="r$.inbound.auth_type.$errors" />
                      </Field>
                      <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                        <Field class="lg:col-span-3" v-bind:data-invalid="r$.inbound.username.$error">
                          <FieldLabel for="inbound.username">
                            {{ "Username" }}
                          </FieldLabel>
                          <Input
                            id="inbound.username"
                            type="text"
                            v-bind:aria-invalid="r$.inbound.username.$error"
                            v-model="r$.inbound.username.$value" />
                          <FieldError class="text-xs" v-if="r$.inbound.username.$error" v-bind:errors="r$.inbound.username.$errors" />
                        </Field>
                        <Field v-bind:data-invalid="r$.inbound.password.$error">
                          <FieldLabel for="inbound.password">
                            {{ "Password" }}
                          </FieldLabel>
                          <Input
                            autocomplete="new-password"
                            id="inbound.password"
                            type="password"
                            v-bind:aria-invalid="r$.inbound.password.$error"
                            v-model="r$.inbound.password.$value" />
                          <FieldError class="text-xs" v-if="r$.inbound.password.$error" v-bind:errors="r$.inbound.password.$errors" />
                        </Field>
                      </div>
                    </div>
                    <div class="grid gap-6 lg:grid-cols-4">
                      <Field v-bind:data-invalid="r$.inbound.fetch_mode.$error">
                        <FieldLabel for="inbound.fetch_mode">
                          {{ "Fetch Mode" }}
                        </FieldLabel>
                        <Select
                          id="inbound.fetch_mode"
                          v-bind:aria-invalid="r$.inbound.fetch_mode.$error"
                          v-model="r$.inbound.fetch_mode.$value">
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="idle">IDLE</SelectItem>
                            <SelectItem value="poll">POLL</SelectItem>
                          </SelectContent>
                        </Select>
                        <FieldError class="text-xs" v-if="r$.inbound.fetch_mode.$error" v-bind:errors="r$.inbound.fetch_mode.$errors" />
                      </Field>
                      <div class="grid gap-6 lg:col-span-3 lg:grid-cols-2">
                        <Field v-bind:data-invalid="r$.inbound.idle_duration.$error">
                          <FieldLabel for="inbound.idle_duration">
                            {{ "IDLE Duration" }}
                          </FieldLabel>
                          <Input
                            id="inbound.idle_duration"
                            type="number"
                            v-bind:aria-invalid="r$.inbound.idle_duration.$error"
                            v-bind:mix="r$.inbound.idle_duration.$rules.minValue.$params[0]"
                            v-bind:max="r$.inbound.idle_duration.$rules.maxValue.$params[0]"
                            v-model="r$.inbound.idle_duration.$value" />
                          <FieldError
                            class="text-xs"
                            v-if="r$.inbound.idle_duration.$error"
                            v-bind:errors="r$.inbound.idle_duration.$errors" />
                        </Field>
                        <Field v-bind:data-invalid="r$.inbound.poll_interval.$error">
                          <FieldLabel for="inbound.poll_interval">
                            {{ "POLL Interval" }}
                          </FieldLabel>
                          <Input
                            id="inbound.poll_interval"
                            type="number"
                            v-bind:aria-invalid="r$.inbound.poll_interval.$error"
                            v-bind:mix="r$.inbound.poll_interval.$rules.minValue.$params[0]"
                            v-bind:max="r$.inbound.poll_interval.$rules.maxValue.$params[0]"
                            v-model="r$.inbound.poll_interval.$value" />
                          <FieldError
                            class="text-xs"
                            v-if="r$.inbound.poll_interval.$error"
                            v-bind:errors="r$.inbound.poll_interval.$errors" />
                        </Field>
                      </div>
                    </div>
                    <div class="grid gap-6 lg:grid-cols-2">
                      <Field v-bind:data-invalid="r$.inbound.mailbox.$error">
                        <FieldLabel for="inbound.mailbox">
                          {{ "Mailbox" }}
                        </FieldLabel>
                        <InputGroup>
                          <InputGroupInput
                            id="inbound.mailbox"
                            type="text"
                            v-bind:aria-invalid="r$.inbound.mailbox.$error"
                            v-model="r$.inbound.mailbox.$value" />
                          <InputGroupAddon align="inline-end" class="pr-2">
                            <Popover>
                              <template v-if="r$.inbound.mailbox.$error">
                                <PopoverTrigger as-child>
                                  <InputGroupButton size="icon-sm" variant="destructive">
                                    <i-hugeicons-alert-01 class="size-5" />
                                  </InputGroupButton>
                                </PopoverTrigger>
                                <PopoverContent class="w-auto p-2 text-sm">
                                  <FieldError v-bind:errors="r$.inbound.mailbox.$errors" />
                                </PopoverContent>
                              </template>
                              <template v-else>
                                <PopoverTrigger as-child>
                                  <InputGroupButton size="icon-sm" variant="ghost">
                                    <i-hugeicons-alert-02 class="size-5" />
                                  </InputGroupButton>
                                </PopoverTrigger>
                                <PopoverContent class="w-auto p-2 text-sm">
                                  <p>{{ "Explain the implications of changing this value (WIP)" }}</p>
                                </PopoverContent>
                              </template>
                            </Popover>
                          </InputGroupAddon>
                        </InputGroup>
                        <FieldError class="text-xs" v-if="r$.inbound.mailbox.$error" v-bind:errors="r$.inbound.mailbox.$errors" />
                      </Field>
                      <Field v-bind:data-invalid="r$.inbound.since.$error">
                        <FieldLabel for="inbound.since">
                          {{ "Since" }}
                        </FieldLabel>
                        <InputGroup>
                          <InputGroupInput
                            id="inbound.since"
                            placeholder="YYYY-MM-DD"
                            type="text"
                            v-bind:aria-invalid="r$.inbound.since.$error"
                            v-model="r$.inbound.since.$value" />
                          <InputGroupAddon align="inline-end" class="pr-2">
                            <Popover>
                              <template v-if="r$.inbound.since.$error">
                                <PopoverTrigger as-child>
                                  <InputGroupButton size="icon-sm" variant="destructive">
                                    <i-hugeicons-alert-01 class="size-5" />
                                  </InputGroupButton>
                                </PopoverTrigger>
                                <PopoverContent class="w-auto p-2 text-sm">
                                  <FieldError v-bind:errors="r$.inbound.since.$errors" />
                                </PopoverContent>
                              </template>
                              <template v-else>
                                <PopoverTrigger as-child>
                                  <InputGroupButton size="icon-sm" variant="ghost">
                                    <i-hugeicons-help-circle class="size-5" />
                                  </InputGroupButton>
                                </PopoverTrigger>
                                <PopoverContent class="w-auto p-2 text-sm">
                                  {{ "Include messages arrived after the given date." }}
                                </PopoverContent>
                              </template>
                            </Popover>
                          </InputGroupAddon>
                        </InputGroup>
                      </Field>
                    </div>
                    <Field
                      orientation="horizontal"
                      v-bind:data-invalid="r$.inbound.ssl_check_hostname.$error"
                      v-bind:data-disabled="r$.inbound.protocol.$value !== 'imap+ssl'">
                      <Checkbox
                        id="inbound.ssl_check_hostname"
                        v-bind:aria-invalid="r$.inbound.ssl_check_hostname.$error"
                        v-bind:disabled="r$.inbound.protocol.$value !== 'imap+ssl'"
                        v-model="r$.inbound.ssl_check_hostname.$value" />
                      <FieldContent>
                        <FieldLabel for="inbound.ssl_check_hostname">
                          {{ "Check server's hostname against its SSL certificate" }}
                        </FieldLabel>
                        <FieldDescription>
                          {{ "This may be required for servers with self-signed certificates" }}
                        </FieldDescription>
                        <FieldError
                          class="text-xs"
                          v-if="r$.inbound.ssl_check_hostname.$error"
                          v-bind:errors="r$.inbound.ssl_check_hostname.$errors" />
                      </FieldContent>
                    </Field>
                  </FieldGroup>
                </FieldSet>
                <Separator class="hidden lg:block" orientation="vertical" />
                <FieldSet>
                  <FieldLegend class="text-center">
                    {{ "Outgoing Mail Server" }}
                  </FieldLegend>
                  <FieldDescription class="text-center">
                    {{ "where the messages will be sent" }}
                  </FieldDescription>
                  <FieldSeparator class="hidden lg:block" />
                  <FieldGroup>
                    <div class="grid gap-6 lg:grid-cols-4">
                      <Field v-bind:data-invalid="r$.outbound.protocol.$error">
                        <FieldLabel for="outbound.protocol">
                          {{ "Protocol" }}
                        </FieldLabel>
                        <Select
                          id="outbound.protocol"
                          v-bind:aria-invalid="r$.outbound.protocol.$error"
                          v-model="r$.outbound.protocol.$value">
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="smtp" disabled>SMTP</SelectItem>
                            <SelectItem value="smtp+tls">SMTP with TLS</SelectItem>
                            <SelectItem value="smtp+ssl">SMTP with SSL</SelectItem>
                          </SelectContent>
                        </Select>
                        <FieldError class="text-xs" v-if="r$.outbound.protocol.$error" v-bind:errors="r$.outbound.protocol.$errors" />
                      </Field>
                      <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                        <Field class="lg:col-span-3" v-bind:data-invalid="r$.outbound.host.$error">
                          <FieldLabel for="outbound.host">
                            {{ "Host" }}
                          </FieldLabel>
                          <Input
                            id="outbound.host"
                            type="text"
                            v-bind:aria-invalid="r$.outbound.host.$error"
                            v-model="r$.outbound.host.$value" />
                          <FieldError class="text-xs" v-if="r$.outbound.host.$error" v-bind:errors="r$.outbound.host.$errors" />
                        </Field>
                        <Field v-bind:data-invalid="r$.outbound.port.$error">
                          <FieldLabel for="outbound.port">
                            {{ "Port" }}
                          </FieldLabel>
                          <Input
                            id="outbound.port"
                            type="number"
                            v-bind:aria-invalid="r$.outbound.port.$error"
                            v-bind:mix="r$.outbound.port.$rules.minValue.$params[0]"
                            v-bind:max="r$.outbound.port.$rules.maxValue.$params[0]"
                            v-model="r$.outbound.port.$value" />
                          <FieldError class="text-xs" v-if="r$.outbound.port.$error" v-bind:errors="r$.outbound.port.$errors" />
                        </Field>
                      </div>
                    </div>
                    <div class="grid gap-6 lg:grid-cols-4">
                      <Field v-bind:data-invalid="r$.outbound.auth_type.$error">
                        <FieldLabel for="outbound.auth_type">
                          {{ "Auth type" }}
                        </FieldLabel>
                        <Select
                          id="outbound.auth_type"
                          v-bind:aria-invalid="r$.outbound.auth_type.$error"
                          v-model="r$.outbound.auth_type.$value">
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="basic">BASIC</SelectItem>
                          </SelectContent>
                        </Select>
                        <FieldDescription class="text-xs">
                          {{ "For Gmail / Google Workspace use BASIC with an App Password." }}
                        </FieldDescription>
                        <FieldError class="text-xs" v-if="r$.outbound.auth_type.$error" v-bind:errors="r$.outbound.auth_type.$errors" />
                      </Field>
                      <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                        <Field class="lg:col-span-3" v-bind:data-invalid="r$.outbound.username.$error">
                          <FieldLabel for="outbound.username">
                            {{ "Username" }}
                          </FieldLabel>
                          <Input
                            id="outbound.username"
                            type="text"
                            v-bind:aria-invalid="r$.outbound.username.$error"
                            v-model="r$.outbound.username.$value" />
                          <FieldError class="text-xs" v-if="r$.outbound.username.$error" v-bind:errors="r$.outbound.username.$errors" />
                        </Field>
                        <Field v-bind:data-invalid="r$.outbound.password.$error">
                          <FieldLabel for="outbound.password">
                            {{ "Password" }}
                          </FieldLabel>
                          <Input
                            autocomplete="new-password"
                            id="outbound.password"
                            type="password"
                            v-bind:aria-invalid="r$.outbound.password.$error"
                            v-model="r$.outbound.password.$value" />
                          <FieldError class="text-xs" v-if="r$.outbound.password.$error" v-bind:errors="r$.outbound.password.$errors" />
                        </Field>
                      </div>
                    </div>
                    <Field v-bind:data-invalid="r$.outbound.from_addr.$error">
                      <FieldLabel for="outbound.from_addr">
                        {{ "From address" }}
                      </FieldLabel>
                      <Input
                        id="outbound.from_addr"
                        type="text"
                        v-bind:aria-invalid="r$.outbound.from_addr.$error"
                        v-model="r$.outbound.from_addr.$value" />
                      <FieldDescription class="text-xs">
                        {{ "Real address used to send replies (e.g. soporte@empresa.com)." }}
                      </FieldDescription>
                      <FieldError class="text-xs" v-if="r$.outbound.from_addr.$error" v-bind:errors="r$.outbound.from_addr.$errors" />
                    </Field>
                    <Field v-bind:data-invalid="r$.outbound.from_name.$error">
                      <FieldLabel for="outbound.from_name">
                        {{ "From name (display)" }}
                      </FieldLabel>
                      <Input
                        id="outbound.from_name"
                        placeholder="Equipo de Devops"
                        type="text"
                        v-bind:aria-invalid="r$.outbound.from_name.$error"
                        v-model="r$.outbound.from_name.$value" />
                      <FieldDescription class="text-xs">
                        {{ "Optional. Shown as the sender name; the real address stays the one above." }}
                      </FieldDescription>
                      <FieldError class="text-xs" v-if="r$.outbound.from_name.$error" v-bind:errors="r$.outbound.from_name.$errors" />
                    </Field>
                    <Field orientation="horizontal" v-bind:data-invalid="r$.outbound.include_agent_name.$error">
                      <Checkbox
                        id="outbound.include_agent_name"
                        v-bind:aria-invalid="r$.outbound.include_agent_name.$error"
                        v-model="r$.outbound.include_agent_name.$value" />
                      <FieldContent>
                        <FieldLabel for="outbound.include_agent_name">
                          {{ "Include the agent's name" }}
                        </FieldLabel>
                        <FieldDescription>
                          {{ "Appends the replying agent, e.g. \"Equipo de Devops (Marcelo Perez)\"." }}
                        </FieldDescription>
                        <FieldError class="text-xs" v-if="r$.outbound.include_agent_name.$error" v-bind:errors="r$.outbound.include_agent_name.$errors" />
                      </FieldContent>
                    </Field>
                    <Field v-bind:data-invalid="r$.outbound.signature_text.$error">
                      <FieldLabel for="outbound.signature_text">
                        {{ "Signature" }}
                      </FieldLabel>
                      <Textarea
                        id="outbound.signature_text"
                        rows="3"
                        placeholder="Saludos,&#10;Equipo de Devops"
                        v-bind:aria-invalid="r$.outbound.signature_text.$error"
                        v-model="r$.outbound.signature_text.$value" />
                      <FieldDescription class="text-xs">
                        {{ "Appended to the footer of every reply." }}
                      </FieldDescription>
                      <FieldError class="text-xs" v-if="r$.outbound.signature_text.$error" v-bind:errors="r$.outbound.signature_text.$errors" />
                    </Field>
                    <Field>
                      <FieldLabel for="outbound.signature_image">
                        {{ "Signature image (PNG/JPG)" }}
                      </FieldLabel>
                      <input
                        id="outbound.signature_image"
                        type="file"
                        accept="image/png,image/jpeg"
                        class="text-sm"
                        v-on:change="(e) => onSignatureImage(e, r$.outbound.signature_image)" />
                      <div v-if="r$.outbound.signature_image.$value" class="mt-2 flex items-center gap-2">
                        <img v-bind:src="r$.outbound.signature_image.$value" alt="firma" class="max-h-16 rounded border" />
                        <Button type="button" size="sm" variant="outline" v-on:click="r$.outbound.signature_image.$value = ''">
                          {{ "Remove" }}
                        </Button>
                      </div>
                    </Field>
                  </FieldGroup>
                </FieldSet>
              </div>
            </FieldGroup>
          </form>
        </ScrollArea>
      </template>
    </CardContent>
  </Card>
</template>
