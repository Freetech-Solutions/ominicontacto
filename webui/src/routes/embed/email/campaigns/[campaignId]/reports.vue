<script lang="ts">
import { useMutation } from "@pinia/colada"
import { useCookies } from "@vueuse/integrations/useCookies"
import { mande, type MandeError } from "mande"
import { toast } from "vue-sonner"
import { t } from "~/i18n"

type Report = {
  correos_recibidos: number
  correos_enviados: number
  correos_fallidos: number
  conversaciones_iniciadas: number
  conversaciones_atendidas: number
  conversaciones_sin_atender: number
  conversaciones_respondidas: number
  conversaciones_reabiertas: number
  conversaciones_calificadas: number
  conversaciones_sin_calificar: number
  dispositions: {
    done: Record<string, number>[]
    not_done: number
  }
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
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Field,
  FieldGroup,
  FieldLabel,
  Input,
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

const startDate = ref<string>(monthAgo())
const endDate = ref<string>(today())

// Metric cards, in display order. `key` indexes the Report payload; `label` is
// an i18n key resolved with t().
const METRICS: { key: keyof Report; label: string }[] = [
  { key: "correos_recibidos", label: "campaign.report.correos_recibidos" },
  { key: "correos_enviados", label: "campaign.report.correos_enviados" },
  { key: "correos_fallidos", label: "campaign.report.correos_fallidos" },
  { key: "conversaciones_iniciadas", label: "campaign.report.conversaciones_iniciadas" },
  { key: "conversaciones_atendidas", label: "campaign.report.conversaciones_atendidas" },
  { key: "conversaciones_sin_atender", label: "campaign.report.conversaciones_sin_atender" },
  { key: "conversaciones_respondidas", label: "campaign.report.conversaciones_respondidas" },
  { key: "conversaciones_reabiertas", label: "campaign.report.conversaciones_reabiertas" },
  { key: "conversaciones_calificadas", label: "campaign.report.conversaciones_calificadas" },
  { key: "conversaciones_sin_calificar", label: "campaign.report.conversaciones_sin_calificar" },
]

const report = useMutation<Report, { start_date: string; end_date: string }, MandeError<any>>({
  mutation(vars) {
    return api.post<Report>(`${campaignId}/report`, vars, {
      headers: { "x-csrftoken": cookies.get("csrftoken") },
    })
  },
  onError(err) {
    toast.error(err.body?.detail ?? err.toString())
  },
})

function handleGenerate() {
  report.mutate({ start_date: startDate.value, end_date: endDate.value })
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
          {{ t("campaign.report.title") }}
        </CardTitle>
        <CardDescription>
          {{ t("campaign.report.description") }}
        </CardDescription>
      </CardHeader>
    </div>
    <CardContent>
      <FieldGroup class="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Field>
          <FieldLabel for="start-date">{{ t("campaign.report.start_date") }}</FieldLabel>
          <Input id="start-date" type="date" v-model="startDate" class="h-10" />
        </Field>
        <Field>
          <FieldLabel for="end-date">{{ t("campaign.report.end_date") }}</FieldLabel>
          <Input id="end-date" type="date" v-model="endDate" class="h-10" />
        </Field>
        <Button v-on:click="handleGenerate" v-bind:disabled="report.isLoading.value" class="h-10">
          <Spinner v-if="report.isLoading.value" class="size-4" />
          <i-hugeicons-mail-01 v-else class="size-5" />
          {{ t("campaign.report.generate") }}
        </Button>
      </FieldGroup>

      <Separator class="my-4" />

      <template v-if="report.status.value === 'error'">
        <Alert variant="destructive">
          <i-hugeicons-alert-circle />
          <AlertTitle>{{ t("campaign.report.error") }}</AlertTitle>
          <AlertDescription v-if="report.error.value">
            <p>{{ report.error.value.body?.detail || report.error.value.toString() }}</p>
          </AlertDescription>
        </Alert>
      </template>
      <template v-else-if="report.data.value">
        <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          <Card v-for="metric in METRICS" v-bind:key="metric.key" class="gap-1 py-4">
            <CardHeader class="px-4">
              <CardDescription class="text-xs">{{ t(metric.label) }}</CardDescription>
            </CardHeader>
            <CardContent class="px-4">
              <span class="text-3xl font-semibold tabular-nums">
                {{ report.data.value[metric.key] }}
              </span>
            </CardContent>
          </Card>
        </div>

        <Separator class="my-4" />

        <h3 class="mb-2 text-sm font-medium">{{ t("campaign.report.dispositions") }}</h3>
        <Table class="text-sm">
          <TableHeader>
            <TableRow>
              <TableHead>{{ t("campaign.report.disposition_name") }}</TableHead>
              <TableHead class="text-right">{{ t("campaign.report.total") }}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="(entry, index) in report.data.value.dispositions.done" v-bind:key="index">
              <TableCell>{{ Object.keys(entry)[0] }}</TableCell>
              <TableCell class="text-right tabular-nums">{{ Object.values(entry)[0] }}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell class="text-muted-foreground">
                {{ t("campaign.report.not_disposed") }}
              </TableCell>
              <TableCell class="text-right tabular-nums">
                <Badge variant="secondary">{{ report.data.value.dispositions.not_done }}</Badge>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </template>
      <template v-else>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon" class="size-14">
              <i-hugeicons-mail-01 class="size-12" />
            </EmptyMedia>
            <EmptyTitle>{{ t("campaign.report.empty_title") }}</EmptyTitle>
            <EmptyDescription>{{ t("campaign.report.empty_description") }}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </template>
    </CardContent>
  </Card>
</template>
