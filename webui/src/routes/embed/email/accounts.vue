<script lang="ts">
import { useMutation, useQuery, useQueryCache } from "@pinia/colada"
import { useCookies } from "@vueuse/integrations/useCookies"
import { mande, type MandeError } from "mande"
import { toast } from "vue-sonner"

type Account = {
  id: number
  name: string
  active: boolean
  messages: number
  test: TestMutationData | null | undefined
}

type Accounts = Account[]

type ResyncMutationData = {
  active: boolean
}

type TestMutationData = {
  inbound: {
    ok: boolean
    errors?: string[]
  }
  outbound: {
    ok: boolean
    errors?: (number | string)[]
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
  CheckboxGroup,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
  Popover,
  PopoverContent,
  PopoverTrigger,
  ScrollArea,
  Separator,
} from "~/shadcn"

const api = mande("/email/api/v1/accounts")
const cache = useQueryCache()
const cookies = useCookies(["csrftoken"])
const selected = ref<number[]>([])

const list = useQuery<Accounts, MandeError<any>, undefined>({
  key: ["email-accounts"],
  query() {
    return api.get<Accounts>()
  },
})

const destroy = useMutation({
  mutation(vars: { id: number }) {
    return api.delete<undefined>(vars.id, {
      headers: {
        "x-csrftoken": cookies.get("csrftoken"),
      },
    })
  },
  onError(err: MandeError<any>) {
    toast.error(err.body?.detail ?? err.toString())
  },
  onSuccess(_, vars) {
    cache.setQueryData<Accounts | undefined>(["email-accounts"], (accounts) =>
      accounts ? accounts.filter((account) => account.id !== vars.id) : undefined,
    )
  },
})

const resync = useMutation({
  mutation(vars: Account) {
    return api.post<ResyncMutationData>(
      `${vars.id}/resync`,
      {},
      {
        headers: { "x-csrftoken": cookies.get("csrftoken") },
      },
    )
  },
  onError(err: MandeError<any>) {
    toast.error(err.body?.detail ?? err.toString())
  },
  onSuccess(data, vars) {
    cache.setQueryData<Accounts | undefined>(["email-accounts"], (accounts) => {
      if (accounts) {
        return accounts.map((account) => (account.id !== vars.id ? account : { ...account, ...data }))
      }
      return accounts
    })
    if (vars.active) {
      toast.success("Sync restarted", {
        description: "The sync process has been restarted",
      })
    } else {
      toast.success("Sync started", {
        description: "The sync process has been started",
      })
    }
  },
})

const test = useMutation({
  mutation(vars: Account) {
    return api.post<TestMutationData>(
      `${vars.id}/test`,
      {
        action: ["inbound", "outbound"],
      },
      {
        headers: {
          "x-csrftoken": cookies.get("csrftoken"),
        },
      },
    )
  },
  onError(err: MandeError<any>) {
    toast.error(err.body?.detail ?? err.toString())
  },
  onSuccess(data, vars) {
    cache.setQueryData<Accounts | undefined>(["email-accounts"], (accounts) => {
      if (accounts) {
        return accounts.map((account) => (account.id !== vars.id ? account : { ...account, test: data }))
      }
      return accounts
    })
    selected.value = selected.value.filter((id) => id !== vars.id)
  },
})

function handleListRefetch() {
  if (!list.isLoading.value) {
    list.refetch(true)
    selected.value = []
  }
}

function handleSelectionDestroy() {
  for (const id of selected.value) {
    destroy.mutate({ id })
  }
  selected.value = []
}

function handleSelectionToggle() {
  if (list.status.value === "success" && list.data.value) {
    if (list.data.value.length === selected.value.length) {
      selected.value = []
    } else {
      selected.value = list.data.value.map((account) => account.id)
    }
  }
}

function handleAccountResync(account: Account) {
  resync.mutate(account)
}

function handleAccountTest(account: Account, open: boolean) {
  if (open && account.test === undefined) {
    account.test = null
    test.mutate(account)
  }
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
          {{ "Email Accounts" }}
        </CardTitle>
        <CardDescription>
          {{ "You can add, edit, or remove email accounts as needed" }}
        </CardDescription>
        <CardAction class="flex h-full gap-2">
          <template v-if="list.data.value?.length">
            <Button size="icon-lg" variant="outline" v-on:click="handleSelectionToggle">
              <template v-if="selected.length === list.data.value?.length">
                <i-hugeicons-checkmark-square-02 class="size-6" />
              </template>
              <template v-else-if="selected.length === 0">
                <i-hugeicons-square class="size-6" />
              </template>
              <template v-else>
                <i-hugeicons-minus-sign-square class="size-6" />
              </template>
            </Button>
            <AlertDialog>
              <AlertDialogTrigger as-child>
                <Button
                  size="icon-lg"
                  v-bind:variant="selected.length === 0 ? 'outline' : 'destructive'"
                  v-bind:disabled="selected.length === 0">
                  <i-hugeicons-delete-02 class="size-6" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {{ "Are you sure?" }}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {{ "You want to delete these accounts?" }}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter v-equalize-children-width>
                  <AlertDialogCancel>
                    {{ "Cancel" }}
                  </AlertDialogCancel>
                  <AlertDialogAction variant="destructive" v-on:click="handleSelectionDestroy">
                    {{ "Delete" }}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <Button size="icon-lg" variant="outline" v-if="false && selected.length > 1" as-child>
              <router-link v-bind:to="{ name: 'embed:email:account:batch-update', query: { ids: selected } }">
                <i-hugeicons-pencil-edit-02 class="size-6" />
              </router-link>
            </Button>
            <Button size="icon-lg" variant="outline" v-else disabled>
              <i-hugeicons-pencil-edit-02 class="size-6" />
            </Button>
          </template>
          <Separator orientation="vertical" class="mx-1" />
          <Button size="icon-lg" variant="outline" v-on:click="handleListRefetch">
            <i-hugeicons-refresh-dot class="size-6" v-bind:class="{ 'animate-spin': list.isLoading.value }" />
          </Button>
          <Button size="icon-lg" variant="default" as-child>
            <router-link v-bind:to="{ name: 'embed:email:account:create' }">
              <i-hugeicons-add-01 class="size-6" />
            </router-link>
          </Button>
        </CardAction>
      </CardHeader>
    </div>
    <CardContent>
      <template v-if="list.status.value === 'pending'"></template>
      <template v-else-if="list.status.value === 'error'">
        <Alert variant="destructive">
          <i-hugeicons-alert-circle />
          <AlertTitle>
            {{ "Unable to retrieve the list of accounts" }}
          </AlertTitle>
          <AlertDescription v-if="list.error.value">
            <p>{{ list.error.value.body?.detail || list.error.value.toString() }}</p>
          </AlertDescription>
        </Alert>
      </template>
      <template v-else-if="list.status.value === 'success'">
        <template v-if="list.data.value?.length">
          <ScrollArea class="-mx-4 max-h-[calc(100vh-150px)] overflow-auto">
            <ItemGroup class="gap-3 px-4 pb-2">
              <Item
                class="has-data-[state=checked]:bg-primary/5 has-data-[state=checked]:border-primary dark:has-data-[state=checked]:bg-primary/10"
                variant="outline"
                v-for="account in list.data.value"
                v-bind:key="account.id">
                <CheckboxGroup v-model="selected" class="self-start">
                  <Checkbox v-bind:id="`it-${account.id}-cb`" v-bind:value="account.id" />
                </CheckboxGroup>
                <ItemContent v-bind:class="{ 'text-muted-foreground': !account.active }">
                  <ItemTitle class="line-clamp-1">
                    <label v-bind:for="`it-${account.id}-cb`">{{ account.name }}</label>
                  </ItemTitle>
                  <ItemDescription>
                    {{ account.messages }}
                    {{ "messages" }}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  <Popover v-on:update:open="handleAccountTest(account, $event)">
                    <PopoverTrigger as-child>
                      <Button size="icon" variant="ghost">
                        <template v-if="account.test === undefined">
                          <i-hugeicons-settings-03 class="size-6" />
                        </template>
                        <template v-else-if="account.test === null">
                          <i-hugeicons-settings-03 class="size-6 animate-pulse" />
                        </template>
                        <template v-else-if="account.test.inbound.ok && account.test.outbound.ok">
                          <i-hugeicons-setting-done-04 class="size-6 text-green-600" />
                        </template>
                        <template v-else>
                          <i-hugeicons-setting-error-04 class="size-6" />
                        </template>
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent class="w-auto p-2 text-sm">
                      <template v-if="account.test">
                        <pre class="bg-muted p-2 text-xs">{{ account.test }}</pre>
                      </template>
                      <template v-else>
                        <i-svg-spinners-bars-scale class="m-2" />
                      </template>
                    </PopoverContent>
                  </Popover>
                  <template v-if="account.active">
                    <Button size="icon" variant="ghost" v-on:click="handleAccountResync(account)">
                      <i-hugeicons-database-sync class="size-6" />
                    </Button>
                  </template>
                  <template v-else>
                    <AlertDialog>
                      <AlertDialogTrigger as-child>
                        <Button size="icon" variant="ghost">
                          <i-hugeicons-database-sync class="size-6" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent class="sm:max-w-sm">
                        <AlertDialogHeader>
                          <AlertDialogTitle class="text-center">
                            {{ "Account is not active" }}
                          </AlertDialogTitle>
                          <AlertDialogDescription class="text-center">
                            {{ "Do you want to proceed with the activation and then with the synchronization?" }}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter v-equalize-children-width class="sm:justify-center">
                          <AlertDialogCancel>
                            {{ "Cancel" }}
                          </AlertDialogCancel>
                          <AlertDialogAction variant="default" v-on:click="handleAccountResync(account)">
                            {{ "Continue" }}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </template>
                  <Button size="icon" variant="ghost" as-child>
                    <router-link v-bind:to="{ name: 'embed:email:account:message:list', params: { accountId: account.id } }">
                      <i-hugeicons-message-multiple-01 class="size-6" />
                    </router-link>
                  </Button>
                  <Button size="icon" variant="ghost" as-child>
                    <router-link v-bind:to="{ name: 'embed:email:account:update', params: { accountId: account.id } }">
                      <i-hugeicons-pencil-edit-02 class="size-6" />
                    </router-link>
                  </Button>
                </ItemActions>
              </Item>
            </ItemGroup>
          </ScrollArea>
        </template>
        <template v-else>
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon" class="size-14">
                <i-hugeicons-mail-at-sign-01 class="size-12" />
              </EmptyMedia>
              <EmptyTitle>
                {{ "You don’t have any accounts yet" }}
              </EmptyTitle>
              <EmptyDescription>
                {{ "Accounts will appear here once they are created" }}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        </template>
      </template>
    </CardContent>
  </Card>
</template>
