from django.db import models


class TruncatedCharField(models.CharField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value and len(value) > self.max_length:
            return value[0 : self.max_length - 3] + "..."  # noqa: E203
        return value


def alters_data(func):
    func.alters_data = True
    return func
