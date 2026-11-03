"""
Django admin helpers.
"""
import copy

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction


class _DryRunRollback(Exception):
    pass


class DryRunSaveForm(forms.ModelForm):
    """
    ModelForm that rehearses the save inside a rolled-back savepoint before the
    admin commits it. Saving some models triggers financial operations via
    signals (completing a transfer, converting a pledge); if those raise a
    ValidationError it is shown on the form instead of a 500 error page.
    """

    def _post_clean(self):
        super()._post_clean()
        if self.errors:
            return
        trial = copy.copy(self.instance)
        trial._state = copy.copy(self.instance._state)
        try:
            with transaction.atomic():
                trial.save()
                raise _DryRunRollback
        except _DryRunRollback:
            pass
        except ValidationError as e:
            self.add_error(None, e.messages)
