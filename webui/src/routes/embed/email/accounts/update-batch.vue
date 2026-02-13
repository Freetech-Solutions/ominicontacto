<script lang="ts">
import { useMutation, useQuery } from "@pinia/colada"
import { useCookies } from "@vueuse/integrations/useCookies"
import { useRouteQuery } from "@vueuse/router"
import { mande, type MandeError } from "mande"
import { toast } from "vue-sonner"
import { type Account } from "./[accountId]/update.vue"
</script>

<script lang="ts" setup>
import { Button, Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle, ScrollArea } from "~/shadcn"

const ids = useRouteQuery<string[]>("ids", [])

const api = mande("/email/api/v1/accounts")
const cookies = useCookies(["csrftoken"])
const router = useRouter()

const retrieve = useQuery<Account[], MandeError<any>, undefined>({
  key: ["email-accounts", ids.value],
  query() {
    return Promise.all(ids.value.map((id) => api.get<Account>(id)))
  },
})

const update = useMutation({
  mutation(accounts: Account[]) {
    return Promise.all(
      accounts.map(({ id, ...data }) =>
        api.put<Account, "json">(id, data, {
          headers: { "x-csrftoken": cookies.get("csrftoken") },
        }),
      ),
    )
  },
  onError(error: MandeError) {},
  onSuccess(data) {
    toast.success("Accounts updated", { description: "Your changes have been saved" })
    router.push({ name: "embed:email:account:list" })
  },
})

watch(retrieve.data, (data) => {})

function handleRefetch() {
  if (!retrieve.isLoading.value) {
    retrieve.refetch(true)
  }
}
async function handleSubmit() {}
</script>

<template lang="html">
  <Card>
    <div class="grid grid-cols-[auto_1fr] gap-2 px-6">
      <Button variant="secondary" class="rounded-full" size="icon-lg" as-child>
        <router-link v-bind:to="{ name: 'embed:email:account:list' }">
          <i-hugeicons-home-02 class="size-8" />
        </router-link>
      </Button>
      <CardHeader class="px-0">
        <CardTitle>
          {{ "Email Accounts" }}
        </CardTitle>
        <CardDescription>
          {{ "You can edit multiple email accounts as needed" }}
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
        <form id="form" v-on:submit.prevent.stop="handleSubmit"></form>
      </ScrollArea>
      <pre class="text-xs">{{ retrieve.data }}</pre>
    </CardContent>
  </Card>
</template>
