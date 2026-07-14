<script lang="ts"></script>

<script lang="ts" setup>
import { Button, Card, CardAction, CardDescription, CardHeader, CardTitle } from "~/shadcn"
</script>

<template lang="html">
  <Card>
    <div class="grid grid-cols-[auto_1fr] gap-2 px-6">
      <Button variant="secondary" class="rounded-full" size="icon-lg" as="div">
        <i-hugeicons-home-02 class="size-8" />
      </Button>
      <CardHeader class="px-0">
        <CardTitle>
          {{ "Email App" }}
        </CardTitle>
        <CardDescription>
          {{ "Email App dashboard" }}
        </CardDescription>
        <CardAction class="flex gap-2"></CardAction>
      </CardHeader>
    </div>
  </Card>
</template>
