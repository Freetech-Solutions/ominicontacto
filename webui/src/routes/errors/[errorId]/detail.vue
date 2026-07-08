<script lang="ts">
import { useErrorsStore } from "~/stores/error"
</script>

<script lang="ts" setup>
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/shadcn"

const { errorId } = defineProps<{ errorId: string }>()
const errorsStore = useErrorsStore()
const error = computed(() => errorsStore.get(errorId))
</script>

<template lang="html">
  <div class="bg-muted h-dvh p-6">
    <Card class="flex h-full flex-col">
      <CardHeader>
        <CardTitle>{{ error?.name }}</CardTitle>
        <CardDescription>{{ error?.code }}</CardDescription>
      </CardHeader>
      <CardContent class="flex-1 overflow-auto">
        <pre class="overflow-auto text-xs">{{ error?.details }}</pre>
      </CardContent>
    </Card>
  </div>
</template>
