import { parseDate } from "@internationalized/date"
import { createRule, type MaybeInput } from "@regle/core"
import { isFilled } from "@regle/rules"

export const iso8601dateString = createRule({
  message: ({ err_msg }) => err_msg ?? "Value must be a valid ISO 8601 date string.",
  validator: (value: MaybeInput<string>) => {
    if (isFilled(value)) {
      try {
        parseDate(value)
        return true
      } catch (err: any) {
        return { $valid: false, err_msg: err.message }
      }
    }
    return true
  },
})
