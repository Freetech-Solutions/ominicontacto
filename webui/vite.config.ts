import TailwindCSS from "@tailwindcss/vite"
import Vue from "@vitejs/plugin-vue"
import VueJsx from "@vitejs/plugin-vue-jsx"
import AutoImport from "unplugin-auto-import/vite"
import IconsResolver from "unplugin-icons/resolver"
import Icons from "unplugin-icons/vite"
import VueComponents from "unplugin-vue-components/vite"
import { defineConfig } from "vite"
import VueDevtools from "vite-plugin-vue-devtools"

export default defineConfig(({ mode }) => {
  const dtsMode = mode === "development" ? "append" : "overwrite"

  return {
    plugins: [
      AutoImport({
        dts: "auto-imports.d.ts",
        dtsMode,
        imports: ["vue", "vue-router"],
      }),
      Icons({
        compiler: "vue3",
      }),
      TailwindCSS(),
      Vue(),
      VueComponents({
        collapseSamePrefixes: true,
        extensions: ["tsx", "vue"],
        directoryAsNamespace: true,
        dts: "components.d.ts",
        resolvers: [IconsResolver({ strict: true })],
        syncMode: dtsMode,
      }),
      VueDevtools(),
      VueJsx(),
    ],
    resolve: {
      tsconfigPaths: true,
    },
    server: {
      proxy: {
        "/email/": {
          target: "https://localhost",
          changeOrigin: true,
          secure: false,
        },
        "/static/": {
          target: "https://localhost",
          changeOrigin: true,
          secure: false,
        },
      },
    },
  }
})
