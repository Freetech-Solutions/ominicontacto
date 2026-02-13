<script lang="ts">
import { useMutation, useQuery } from "@pinia/colada"
import { useRegle, type RegleExternalErrorTree } from "@regle/core"
import { boolean, maxLength, maxValue, minValue, number, required } from "@regle/rules"
import { useCookies } from "@vueuse/integrations/useCookies"
import { mande, type MandeError } from "mande"
import { toast } from "vue-sonner"
import { iso8601dateString } from "~/rules/iso8601dateString"

type Account = {
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
  }
}
</script>

<script lang="ts" setup>
import {
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
  Skeleton,
  Switch,
} from "~/shadcn"

const api = mande("/email/api/v1/accounts")
const cookies = useCookies(["csrftoken"])
const router = useRouter()

const { r$: form } = useRegle(
  <Account>{
    name: "",
    active: true,
    inbound: {
      protocol: "imap+ssl",
      host: "",
      port: 993,
      auth_type: "basic",
      username: "",
      password: "",
      fetch_mode: "idle",
      idle_duration: 180,
      poll_interval: 180,
      mailbox: "Inbox",
      since: "",
      ssl_check_hostname: true,
    },
    outbound: {
      protocol: "smtp+tls",
      host: "",
      port: 587,
      auth_type: "basic",
      username: "",
      password: "",
      from_addr: "",
    },
  },
  {
    name: { required, maxLength: maxLength(100) },
    active: { required, boolean },
    inbound: {
      protocol: { required },
      host: { required },
      port: { required, number, minValue: minValue(0), maxValue: maxValue(65535) },
      auth_type: { required },
      username: { required },
      password: { required },
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
      password: { required },
      from_addr: { required },
    },
  },
  {
    id: "account:+",
    externalErrors: ref<RegleExternalErrorTree<Account>>({}),
  },
)

const create = useMutation({
  mutation(data: Account) {
    return api.post<Account, "json">(data, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(error: MandeError) {
    form.$setExternalErrors(error.body)
  },
  onSuccess() {
    toast.success("Account created", {
      description: "Your changes have been saved.",
    })
    router.push({ name: "embed:email:account:list" })
  },
})

function handleRefetch() {
  form.$reset({ toOriginalState: true })
}

async function handleSubmit() {
  const { valid, data } = await form.$validate()
  if (valid) {
    create.mutate(data as Account)
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
          <Button size="icon-lg" variant="outline" v-on:click="handleRefetch">
            <i-hugeicons-repost class="size-6" />
          </Button>
          <Button size="icon-lg" type="submit" variant="outline" form="form">
            <i-hugeicons-save class="size-6" />
          </Button>
        </CardAction>
      </CardHeader>
    </div>
    <CardContent>
      <ScrollArea class="-mx-4 max-h-[calc(100vh-150px)] overflow-auto">
        <form id="form" v-on:submit.prevent.stop="handleSubmit">
          <FieldGroup class="px-4">
            <Field v-bind:data-invalid="form.name.$error">
              <FieldLabel for="name">
                {{ "Name" }}
              </FieldLabel>
              <InputGroup>
                <InputGroupInput id="name" type="text" v-bind:aria-invalid="form.name.$error" v-model="form.name.$value" />
                <InputGroupAddon align="inline-end" class="text-xs" v-if="form.name.$value">
                  {{ form.name.$value?.length }}/{{ form.name.$rules.maxLength.$params[0] }}
                </InputGroupAddon>
              </InputGroup>
              <FieldError class="text-xs" v-if="form.name.$error" v-bind:errors="form.name.$errors" />
            </Field>
            <Field orientation="horizontal" v-bind:data-invalid="form.active.$error">
              <Switch id="active" v-bind:aria-invalid="form.active.$error" v-model="form.active.$value" />
              <FieldContent>
                <FieldLabel for="active">
                  {{ "Active" }}
                </FieldLabel>
                <FieldDescription>
                  {{ "You can deactivate the account to prevent further interactions" }}
                </FieldDescription>
                <FieldError class="text-xs" v-if="form.active.$error" v-bind:errors="form.active.$errors" />
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
                    <Field v-bind:data-invalid="form.inbound.protocol.$error">
                      <FieldLabel for="inbound.protocol">
                        {{ "Protocol" }}
                      </FieldLabel>
                      <Select
                        id="inbound.protocol"
                        v-bind:aria-invalid="form.inbound.protocol.$error"
                        v-model="form.inbound.protocol.$value">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="imap" disabled>IMAP</SelectItem>
                          <SelectItem value="imap+tls" disabled>IMAP with TLS</SelectItem>
                          <SelectItem value="imap+ssl">IMAP with SSL</SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldError class="text-xs" v-if="form.inbound.protocol.$error" v-bind:errors="form.inbound.protocol.$errors" />
                    </Field>
                    <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                      <Field class="lg:col-span-3" v-bind:data-invalid="form.inbound.host.$error">
                        <FieldLabel for="inbound.host">
                          {{ "Host" }}
                        </FieldLabel>
                        <Input
                          id="inbound.host"
                          type="text"
                          v-bind:aria-invalid="form.inbound.host.$error"
                          v-model="form.inbound.host.$value" />
                        <FieldError class="text-xs" v-if="form.inbound.host.$error" v-bind:errors="form.inbound.host.$errors" />
                      </Field>
                      <Field v-bind:data-invalid="form.inbound.port.$error">
                        <FieldLabel for="inbound.port">
                          {{ "Port" }}
                        </FieldLabel>
                        <Input
                          id="inbound.port"
                          type="number"
                          v-bind:aria-invalid="form.inbound.port.$error"
                          v-bind:mix="form.inbound.port.$rules.minValue.$params[0]"
                          v-bind:max="form.inbound.port.$rules.maxValue.$params[0]"
                          v-model="form.inbound.port.$value" />
                        <FieldError class="text-xs" v-if="form.inbound.port.$error" v-bind:errors="form.inbound.port.$errors" />
                      </Field>
                    </div>
                  </div>
                  <div class="grid gap-6 lg:grid-cols-4">
                    <Field v-bind:data-invalid="form.inbound.auth_type.$error">
                      <FieldLabel for="inbound.auth_type">
                        {{ "Auth type" }}
                      </FieldLabel>
                      <Select
                        id="inbound.auth_type"
                        v-bind:aria-invalid="form.inbound.auth_type.$error"
                        v-model="form.inbound.auth_type.$value">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="basic">BASIC</SelectItem>
                          <SelectItem value="xoauth2">XOAUTH2</SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldError class="text-xs" v-if="form.inbound.auth_type.$error" v-bind:errors="form.inbound.auth_type.$errors" />
                    </Field>
                    <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                      <Field class="lg:col-span-3" v-bind:data-invalid="form.inbound.username.$error">
                        <FieldLabel for="inbound.username">
                          {{ "Username" }}
                        </FieldLabel>
                        <Input
                          id="inbound.username"
                          type="text"
                          v-bind:aria-invalid="form.inbound.username.$error"
                          v-model="form.inbound.username.$value" />
                        <FieldError class="text-xs" v-if="form.inbound.username.$error" v-bind:errors="form.inbound.username.$errors" />
                      </Field>
                      <Field v-bind:data-invalid="form.inbound.password.$error">
                        <FieldLabel for="inbound.password">
                          {{ "Password" }}
                        </FieldLabel>
                        <Input
                          autocomplete="new-password"
                          id="inbound.password"
                          type="password"
                          v-bind:aria-invalid="form.inbound.password.$error"
                          v-model="form.inbound.password.$value" />
                        <FieldError class="text-xs" v-if="form.inbound.password.$error" v-bind:errors="form.inbound.password.$errors" />
                      </Field>
                    </div>
                  </div>
                  <div class="grid gap-6 lg:grid-cols-4">
                    <Field v-bind:data-invalid="form.inbound.fetch_mode.$error">
                      <FieldLabel for="inbound.fetch_mode">
                        {{ "Fetch Mode" }}
                      </FieldLabel>
                      <Select
                        id="inbound.fetch_mode"
                        v-bind:aria-invalid="form.inbound.fetch_mode.$error"
                        v-model="form.inbound.fetch_mode.$value">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="idle">IDLE</SelectItem>
                          <SelectItem value="poll">POLL</SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldError class="text-xs" v-if="form.inbound.fetch_mode.$error" v-bind:errors="form.inbound.fetch_mode.$errors" />
                    </Field>
                    <div class="grid gap-6 lg:col-span-3 lg:grid-cols-2">
                      <Field v-bind:data-invalid="form.inbound.idle_duration.$error">
                        <FieldLabel for="inbound.idle_duration">
                          {{ "IDLE Duration" }}
                        </FieldLabel>
                        <Input
                          id="inbound.idle_duration"
                          type="number"
                          v-bind:aria-invalid="form.inbound.idle_duration.$error"
                          v-bind:mix="form.inbound.idle_duration.$rules.minValue.$params[0]"
                          v-bind:max="form.inbound.idle_duration.$rules.maxValue.$params[0]"
                          v-model="form.inbound.idle_duration.$value" />
                        <FieldError
                          class="text-xs"
                          v-if="form.inbound.idle_duration.$error"
                          v-bind:errors="form.inbound.idle_duration.$errors" />
                      </Field>
                      <Field v-bind:data-invalid="form.inbound.poll_interval.$error">
                        <FieldLabel for="inbound.poll_interval">
                          {{ "POLL Interval" }}
                        </FieldLabel>
                        <Input
                          id="inbound.poll_interval"
                          type="number"
                          v-bind:aria-invalid="form.inbound.poll_interval.$error"
                          v-bind:mix="form.inbound.poll_interval.$rules.minValue.$params[0]"
                          v-bind:max="form.inbound.poll_interval.$rules.maxValue.$params[0]"
                          v-model="form.inbound.poll_interval.$value" />
                        <FieldError
                          class="text-xs"
                          v-if="form.inbound.poll_interval.$error"
                          v-bind:errors="form.inbound.poll_interval.$errors" />
                      </Field>
                    </div>
                  </div>
                  <div class="grid gap-6 lg:grid-cols-2">
                    <Field v-bind:data-invalid="form.inbound.mailbox.$error">
                      <FieldLabel for="inbound.mailbox">
                        {{ "Mailbox" }}
                      </FieldLabel>
                      <InputGroup>
                        <InputGroupInput
                          id="inbound.mailbox"
                          type="text"
                          v-bind:aria-invalid="form.inbound.mailbox.$error"
                          v-model="form.inbound.mailbox.$value" />
                        <InputGroupAddon align="inline-end" class="pr-2">
                          <Popover>
                            <template v-if="form.inbound.mailbox.$error">
                              <PopoverTrigger as-child>
                                <InputGroupButton size="icon-sm" variant="destructive">
                                  <i-hugeicons-alert-01 class="size-5" />
                                </InputGroupButton>
                              </PopoverTrigger>
                              <PopoverContent class="w-auto p-2 text-sm">
                                <FieldError v-bind:errors="form.inbound.mailbox.$errors" />
                              </PopoverContent>
                            </template>
                            <template v-else>
                              <PopoverTrigger as-child>
                                <InputGroupButton size="icon-sm" variant="ghost">
                                  <i-hugeicons-alert-02 class="size-5" />
                                </InputGroupButton>
                              </PopoverTrigger>
                              <PopoverContent class="w-auto p-2 text-sm">
                                <p>{{ "Explain the implications of changing this value later (WIP)" }}</p>
                              </PopoverContent>
                            </template>
                          </Popover>
                        </InputGroupAddon>
                      </InputGroup>
                      <FieldError class="text-xs" v-if="form.inbound.mailbox.$error" v-bind:errors="form.inbound.mailbox.$errors" />
                    </Field>
                    <Field v-bind:data-invalid="form.inbound.since.$error">
                      <FieldLabel for="inbound.since">
                        {{ "Since" }}
                      </FieldLabel>
                      <InputGroup>
                        <InputGroupInput
                          id="inbound.since"
                          placeholder="YYYY-MM-DD"
                          type="text"
                          v-bind:aria-invalid="form.inbound.since.$error"
                          v-model="form.inbound.since.$value" />
                        <InputGroupAddon align="inline-end" class="pr-2">
                          <Popover>
                            <template v-if="form.inbound.since.$error">
                              <PopoverTrigger as-child>
                                <InputGroupButton size="icon-sm" variant="destructive">
                                  <i-hugeicons-alert-01 class="size-5" />
                                </InputGroupButton>
                              </PopoverTrigger>
                              <PopoverContent class="w-auto p-2 text-sm">
                                <FieldError v-bind:errors="form.inbound.since.$errors" />
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
                    v-bind:data-invalid="form.inbound.ssl_check_hostname.$error"
                    v-bind:data-disabled="form.inbound.protocol.$value !== 'imap+ssl'">
                    <Checkbox
                      id="inbound.ssl_check_hostname"
                      v-bind:aria-invalid="form.inbound.ssl_check_hostname.$error"
                      v-bind:disabled="form.inbound.protocol.$value !== 'imap+ssl'"
                      v-model="form.inbound.ssl_check_hostname.$value" />
                    <FieldContent>
                      <FieldLabel for="inbound.ssl_check_hostname">
                        {{ "Check server's hostname against its SSL certificate" }}
                      </FieldLabel>
                      <FieldDescription>
                        {{ "This may be required for servers with self-signed certificates" }}
                      </FieldDescription>
                      <FieldError
                        class="text-xs"
                        v-if="form.inbound.ssl_check_hostname.$error"
                        v-bind:errors="form.inbound.ssl_check_hostname.$errors" />
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
                    <Field v-bind:data-invalid="form.outbound.protocol.$error">
                      <FieldLabel for="outbound.protocol">
                        {{ "Protocol" }}
                      </FieldLabel>
                      <Select
                        id="outbound.protocol"
                        v-bind:aria-invalid="form.outbound.protocol.$error"
                        v-model="form.outbound.protocol.$value">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="smtp" disabled>SMTP</SelectItem>
                          <SelectItem value="smtp+tls">SMTP with TLS</SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldError class="text-xs" v-if="form.outbound.protocol.$error" v-bind:errors="form.outbound.protocol.$errors" />
                    </Field>
                    <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                      <Field class="lg:col-span-3" v-bind:data-invalid="form.outbound.host.$error">
                        <FieldLabel for="outbound.host">
                          {{ "Host" }}
                        </FieldLabel>
                        <Input
                          id="outbound.host"
                          type="text"
                          v-bind:aria-invalid="form.outbound.host.$error"
                          v-model="form.outbound.host.$value" />
                        <FieldError class="text-xs" v-if="form.outbound.host.$error" v-bind:errors="form.outbound.host.$errors" />
                      </Field>
                      <Field v-bind:data-invalid="form.outbound.port.$error">
                        <FieldLabel for="outbound.port">
                          {{ "Port" }}
                        </FieldLabel>
                        <Input
                          id="outbound.port"
                          type="number"
                          v-bind:aria-invalid="form.outbound.port.$error"
                          v-bind:mix="form.outbound.port.$rules.minValue.$params[0]"
                          v-bind:max="form.outbound.port.$rules.maxValue.$params[0]"
                          v-model="form.outbound.port.$value" />
                        <FieldError class="text-xs" v-if="form.outbound.port.$error" v-bind:errors="form.outbound.port.$errors" />
                      </Field>
                    </div>
                  </div>
                  <div class="grid gap-6 lg:grid-cols-4">
                    <Field v-bind:data-invalid="form.outbound.auth_type.$error">
                      <FieldLabel for="outbound.auth_type">
                        {{ "Auth type" }}
                      </FieldLabel>
                      <Select
                        id="outbound.auth_type"
                        v-bind:aria-invalid="form.outbound.auth_type.$error"
                        v-model="form.outbound.auth_type.$value">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="basic">BASIC</SelectItem>
                          <SelectItem value="xoauth2">XOAUTH2</SelectItem>
                        </SelectContent>
                      </Select>
                      <FieldError class="text-xs" v-if="form.outbound.auth_type.$error" v-bind:errors="form.outbound.auth_type.$errors" />
                    </Field>
                    <div class="grid gap-6 lg:col-span-3 lg:grid-cols-4">
                      <Field class="lg:col-span-3" v-bind:data-invalid="form.outbound.username.$error">
                        <FieldLabel for="outbound.username">
                          {{ "Username" }}
                        </FieldLabel>
                        <Input
                          id="outbound.username"
                          type="text"
                          v-bind:aria-invalid="form.outbound.username.$error"
                          v-model="form.outbound.username.$value" />
                        <FieldError class="text-xs" v-if="form.outbound.username.$error" v-bind:errors="form.outbound.username.$errors" />
                      </Field>
                      <Field v-bind:data-invalid="form.outbound.password.$error">
                        <FieldLabel for="outbound.password">
                          {{ "Password" }}
                        </FieldLabel>
                        <Input
                          autocomplete="new-password"
                          id="outbound.password"
                          type="password"
                          v-bind:aria-invalid="form.outbound.password.$error"
                          v-model="form.outbound.password.$value" />
                        <FieldError class="text-xs" v-if="form.outbound.password.$error" v-bind:errors="form.outbound.password.$errors" />
                      </Field>
                    </div>
                  </div>
                  <Field v-bind:data-invalid="form.outbound.from_addr.$error">
                    <FieldLabel for="outbound.from_addr">
                      {{ "From address" }}
                    </FieldLabel>
                    <Input
                      id="outbound.from_addr"
                      type="text"
                      v-bind:aria-invalid="form.outbound.from_addr.$error"
                      v-model="form.outbound.from_addr.$value" />
                    <FieldError class="text-xs" v-if="form.outbound.from_addr.$error" v-bind:errors="form.outbound.from_addr.$errors" />
                  </Field>
                </FieldGroup>
              </FieldSet>
            </div>
          </FieldGroup>
        </form>
      </ScrollArea>
    </CardContent>
  </Card>
</template>
