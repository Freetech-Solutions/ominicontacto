import { type MandeError } from "mande"
import { type RouteLocationNormalizedLoadedGeneric, type RouteRecordRaw } from "vue-router"
import { useErrorsStore } from "~/stores/error"
import { useSelfStore } from "~/stores/self"

export const routes: RouteRecordRaw[] = [
  {
    path: "/accounts",
    children: [
      {
        path: "login",
        name: "accounts:login",
        component: () => import("./accounts/login.vue"),
      },
    ],
  },
  {
    path: "/embed",
    component: () => import("./embed.vue"),
    children: [
      {
        path: "email",
        children: [
          {
            path: "",
            name: "embed:email",
            component: () => import("./embed/email.vue"),
          },
          {
            path: "campaigns",
            children: [
              {
                path: ":campaignId",
                children: [
                  {
                    path: "conversations",
                    name: "embed:email:campaign:conversations",
                    component: () => import("./embed/email/campaigns/[campaignId]/conversations.vue"),
                    props: ({ params }) => ({ campaignId: Number(params.campaignId) }),
                  },
                  {
                    path: "reports",
                    name: "embed:email:campaign:reports",
                    component: () => import("./embed/email/campaigns/[campaignId]/reports.vue"),
                    props: ({ params }) => ({ campaignId: Number(params.campaignId) }),
                  },
                ],
              },
            ],
          },
          {
            path: "accounts",
            children: [
              {
                path: "",
                name: "embed:email:account:list",
                component: () => import("./embed/email/accounts.vue"),
              },
              {
                path: "create",
                name: "embed:email:account:create",
                component: () => import("./embed/email/accounts/create.vue"),
              },
              {
                path: "update-batch",
                name: "embed:email:account:batch-update",
                component: () => import("./embed/email/accounts/update-batch.vue"),
              },
              {
                path: ":accountId",
                children: [
                  {
                    path: "update",
                    name: "embed:email:account:update",
                    component: () => import("./embed/email/accounts/[accountId]/update.vue"),
                    props: ({ params }) => ({ accountId: Number(params.accountId) }),
                  },
                  {
                    path: "messages",
                    component: () => import("./embed/email/accounts/[accountId]/messages.vue"),
                    props: ({ params }) => ({ accountId: Number(params.accountId) }),
                    children: [
                      {
                        path: "",
                        name: "embed:email:account:message:list",
                        component: () => import("./embed/email/accounts/[accountId]/messages/list.vue"),
                        props: ({ params }) => ({ accountId: Number(params.accountId) }),
                      },
                      {
                        path: ":messageId",
                        children: [
                          {
                            path: "detail",
                            name: "embed:email:account:message:detail",
                            component: () => import("./embed/email/accounts/[accountId]/messages/[messageId]/detail.vue"),
                            props: ({ params }) => ({ accountId: Number(params.accountId), messageId: Number(params.messageId) }),
                          },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
  {
    path: "/errors",
    children: [
      {
        path: ":errorId",
        name: "error:detail",
        component: () => import("./errors/[errorId]/detail.vue"),
        props: ({ params }) => ({ errorId: params.errorId }),
      },
    ],
  },
  {
    path: "/workspace",
    children: [
      {
        path: "",
        name: "workspace",
        component: () => import("./workspace.vue"),
      },
    ],
  },
]

export async function beforeResolve(to: RouteLocationNormalizedLoadedGeneric) {
  if (to.name === "error:detail") {
    return
  }

  const selfStore = useSelfStore()
  const errorsStore = useErrorsStore()

  if (!selfStore.initialized) {
    try {
      await selfStore.initialize()
    } catch (error: any) {
      const { response }: { response: Response } = error as MandeError
      const details =
        response.headers.get("Content-Type") === "text/plain; charset=utf-8"
          ? await response.text()
          : response.headers.get("Content-Type") === "application/json"
            ? await response.json()
            : null
      const errorId = errorsStore.append({
        code: response.status,
        name: response.statusText,
        details,
      })
      return { name: "error:detail", params: { errorId } }
    }
  }
  if (selfStore.userIsAnonymous) {
    if (to.name !== "accounts:login") {
      return { name: "accounts:login" }
    }
  }
}
