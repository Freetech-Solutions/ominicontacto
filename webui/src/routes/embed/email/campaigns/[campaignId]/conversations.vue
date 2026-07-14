<script lang="ts">
import { useMutation, useQuery } from "@pinia/colada"
import { useCookies } from "@vueuse/integrations/useCookies"
import { mande, type MandeError } from "mande"
import { toast } from "vue-sonner"
import { t } from "~/i18n"

type Agent = { id: number; name: string }

type Conversation = {
  id: number
  subject: string
  client_mail: string
  client_name: string
  status: string
  is_active: boolean
  is_disposition: boolean
  timestamp: string
  date_last_interaction: string | null
  account_name: string
  campaign_name: string
  agent: Agent | null
  disposition: string
  messages: number
  received: number
  sent: number
}

type Message = {
  id: number
  direction: string
  date: string | null
  subject: string
  from_mail: string
  from_name: string
  to_mail: string
  to_name: string
  body_html: string
  body_text: string
  attachments: { name: string; url: string }[]
}

type ConversationDetail = Conversation & { mensajes: Message[] }

type Filters = {
  start_date: string
  end_date: string
  email: string
  agents: number[]
}
</script>

<script lang="ts" setup>
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Field,
  FieldGroup,
  FieldLabel,
  Input,
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemHeader,
  ScrollArea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/shadcn"

const { campaignId } = defineProps<{ campaignId: number }>()

const api = mande("/email/api/v1/campaigns")
const cookies = useCookies(["csrftoken"])

function today(): string {
  return new Date().toISOString().slice(0, 10)
}
function monthAgo(): string {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}
function formatDate(value: string | null): string {
  if (!value) return "—"
  const d = new Date(value)
  return isNaN(d.getTime()) ? value : d.toLocaleString()
}

const startDate = ref<string>(monthAgo())
const endDate = ref<string>(today())
const email = ref<string>("")
// "all" -> all, "-1" -> sin agente, "<id>" -> that agent
const agentFilter = ref<string>("all")

const agents = useQuery<Agent[], MandeError<any>, undefined>({
  key: ["email-campaign-agents", campaignId],
  query() {
    return api.get<Agent[]>(`${campaignId}/agents`)
  },
})

const conversations = useMutation<Conversation[], Filters, MandeError<any>>({
  mutation(vars) {
    return api.post<Conversation[]>(`${campaignId}/conversations`, vars, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(err) {
    toast.error(err.body?.detail ?? err.toString())
  },
})

function handleSearch() {
  const agentList = agentFilter.value === "all" ? [] : [Number(agentFilter.value)]
  conversations.mutate({
    start_date: startDate.value,
    end_date: endDate.value,
    email: email.value.trim(),
    agents: agentList,
  })
}

// --- Detail dialog ---------------------------------------------------------

const detailOpen = ref(false)
const detail = useMutation<ConversationDetail, number, MandeError<any>>({
  mutation(id) {
    return api.get<ConversationDetail>(`${campaignId}/conversations/${id}`)
  },
  onError(err) {
    toast.error(err.body?.detail ?? err.toString())
  },
})

function openDetail(conversation: Conversation) {
  detailOpen.value = true
  detail.mutate(conversation.id)
}
</script>

<template lang="html">
  <Card>
    <div class="grid grid-cols-[auto_1fr] gap-2 px-6">
      <Button class="rounded-full" variant="secondary" size="icon-lg" as-child>
        <router-link v-bind:to="{ name: 'embed:email' }">
          <i-hugeicons-mail-01 class="size-8" />
        </router-link>
      </Button>
      <CardHeader class="px-0">
        <CardTitle>
          {{ t("campaign.conversations.title") }}
        </CardTitle>
        <CardDescription>
          {{ t("campaign.conversations.description") }}
        </CardDescription>
      </CardHeader>
    </div>
    <CardContent>
      <FieldGroup class="flex flex-col gap-3 lg:flex-row lg:items-end">
        <Field>
          <FieldLabel for="start-date">{{ t("campaign.conversations.start_date") }}</FieldLabel>
          <Input id="start-date" type="date" v-model="startDate" class="h-10" />
        </Field>
        <Field>
          <FieldLabel for="end-date">{{ t("campaign.conversations.end_date") }}</FieldLabel>
          <Input id="end-date" type="date" v-model="endDate" class="h-10" />
        </Field>
        <Field>
          <FieldLabel for="email">{{ t("campaign.conversations.email") }}</FieldLabel>
          <Input
            id="email"
            v-model="email"
            class="h-10"
            v-bind:placeholder="t('campaign.conversations.email_placeholder')" />
        </Field>
        <Field>
          <FieldLabel>{{ t("campaign.conversations.agent") }}</FieldLabel>
          <Select v-model="agentFilter">
            <SelectTrigger class="h-10 w-full">
              <SelectValue v-bind:placeholder="t('campaign.conversations.all_agents')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{{ t("campaign.conversations.all_agents") }}</SelectItem>
              <SelectItem value="-1">{{ t("campaign.conversations.no_agent") }}</SelectItem>
              <SelectItem v-for="agent in agents.data.value || []" v-bind:key="agent.id" v-bind:value="String(agent.id)">
                {{ agent.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Button v-on:click="handleSearch" v-bind:disabled="conversations.isLoading.value" class="h-10">
          <Spinner v-if="conversations.isLoading.value" class="size-4" />
          <i-hugeicons-refresh-dot v-else class="size-5" />
          {{ t("campaign.conversations.search") }}
        </Button>
      </FieldGroup>

      <Separator class="my-4" />

      <template v-if="conversations.status.value === 'error'">
        <Alert variant="destructive">
          <i-hugeicons-alert-circle />
          <AlertTitle>{{ t("campaign.conversations.error") }}</AlertTitle>
          <AlertDescription v-if="conversations.error.value">
            <p>{{ conversations.error.value.body?.detail || conversations.error.value.toString() }}</p>
          </AlertDescription>
        </Alert>
      </template>
      <template v-else-if="conversations.data.value">
        <template v-if="conversations.data.value.length">
          <ScrollArea class="-mx-4 max-h-[calc(100vh-260px)] overflow-auto">
            <div class="px-4">
              <Table class="text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>{{ t("campaign.conversations.col_agent") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_start") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_subject") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_email") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_account") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_last") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_status") }}</TableHead>
                    <TableHead class="text-right">{{ t("campaign.conversations.col_emails") }}</TableHead>
                    <TableHead>{{ t("campaign.conversations.col_disposition") }}</TableHead>
                    <TableHead class="text-right">{{ t("campaign.conversations.col_options") }}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="conversation in conversations.data.value" v-bind:key="conversation.id">
                    <TableCell>{{ conversation.agent?.name || "—" }}</TableCell>
                    <TableCell class="whitespace-nowrap">{{ formatDate(conversation.timestamp) }}</TableCell>
                    <TableCell class="max-w-[16rem] truncate">{{ conversation.subject || "—" }}</TableCell>
                    <TableCell>{{ conversation.client_mail }}</TableCell>
                    <TableCell>{{ conversation.account_name }}</TableCell>
                    <TableCell class="whitespace-nowrap">{{ formatDate(conversation.date_last_interaction) }}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{{ t(`campaign.conversations.status.${conversation.status}`) }}</Badge>
                    </TableCell>
                    <TableCell class="text-right tabular-nums">
                      <span v-bind:title="`↓ ${conversation.received} · ↑ ${conversation.sent}`">
                        {{ conversation.messages }}
                      </span>
                    </TableCell>
                    <TableCell>{{ conversation.disposition || "—" }}</TableCell>
                    <TableCell class="text-right">
                      <Button size="icon" variant="ghost" v-on:click="openDetail(conversation)">
                        <i-hugeicons-microscope class="size-5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </ScrollArea>
        </template>
        <template v-else>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon" class="size-14">
                <i-hugeicons-mail-at-sign-01 class="size-12" />
              </EmptyMedia>
              <EmptyTitle>{{ t("campaign.conversations.empty_title") }}</EmptyTitle>
              <EmptyDescription>{{ t("campaign.conversations.empty_description") }}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </template>
      </template>
      <template v-else>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon" class="size-14">
              <i-hugeicons-mail-at-sign-01 class="size-12" />
            </EmptyMedia>
            <EmptyTitle>{{ t("campaign.conversations.prompt_title") }}</EmptyTitle>
            <EmptyDescription>{{ t("campaign.conversations.prompt_description") }}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </template>
    </CardContent>
  </Card>

  <Dialog v-model:open="detailOpen">
    <DialogContent class="max-h-[88vh] overflow-hidden sm:max-w-3xl">
      <DialogHeader>
        <DialogTitle class="truncate">
          {{ detail.data.value?.subject || t("campaign.conversations.detail_title") }}
        </DialogTitle>
        <DialogDescription>
          {{ detail.data.value?.client_name }} &lt;{{ detail.data.value?.client_mail }}&gt;
        </DialogDescription>
      </DialogHeader>
      <template v-if="detail.isLoading.value">
        <div class="flex items-center justify-center p-8">
          <Spinner class="size-8" />
        </div>
      </template>
      <template v-else-if="detail.data.value">
        <ScrollArea class="max-h-[68vh] overflow-auto pr-2">
          <ItemGroup class="gap-3">
            <Item
              v-for="message in detail.data.value.mensajes"
              v-bind:key="message.id"
              variant="outline"
              v-bind:class="message.direction === 'outbound' ? 'bg-green-50 dark:bg-green-950/30' : ''">
              <ItemHeader class="flex-col items-stretch gap-1">
                <div class="flex items-center justify-between gap-2">
                  <Badge v-bind:variant="message.direction === 'outbound' ? 'default' : 'secondary'">
                    {{ message.direction === "outbound"
                      ? t("campaign.conversations.outbound")
                      : t("campaign.conversations.inbound") }}
                  </Badge>
                  <span class="text-muted-foreground text-xs whitespace-nowrap">
                    {{ formatDate(message.date) }}
                  </span>
                </div>
                <span class="text-xs">
                  <strong>{{ message.from_name || message.from_mail }}</strong>
                  &lt;{{ message.from_mail }}&gt; → {{ message.to_mail }}
                </span>
              </ItemHeader>
              <ItemContent>
                <iframe
                  v-if="message.body_html"
                  class="h-64 w-full rounded border bg-white"
                  v-bind:srcdoc="message.body_html"
                  sandbox=""></iframe>
                <pre v-else class="bg-muted overflow-auto rounded border p-2 text-xs whitespace-pre-wrap">{{ message.body_text }}</pre>
                <ItemDescription v-if="message.attachments.length" class="mt-1">
                  <span v-for="attachment in message.attachments" v-bind:key="attachment.url" class="mr-2">
                    <Button variant="link" size="sm" as-child>
                      <a v-bind:href="attachment.url" target="_blank">
                        <i-hugeicons-attachment-01 class="size-4" />
                        {{ attachment.name }}
                      </a>
                    </Button>
                  </span>
                </ItemDescription>
              </ItemContent>
            </Item>
          </ItemGroup>
        </ScrollArea>
      </template>
    </DialogContent>
  </Dialog>
</template>
