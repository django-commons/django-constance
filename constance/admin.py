import json
from collections import OrderedDict
from datetime import date
from datetime import datetime
from operator import itemgetter

from django import forms
from django import get_version
from django.apps import apps
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.models import CHANGE
from django.contrib.admin.models import LogEntry
from django.contrib.admin.options import csrf_protect_m
from django.contrib.admin.views.main import PAGE_VAR
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.formats import localize
from django.utils.translation import gettext_lazy as _

from . import LazyConfig
from . import settings
from .forms import ConstanceForm
from .utils import get_values

config = LazyConfig()


class ConstanceAdmin(admin.ModelAdmin):
    change_list_template = "admin/constance/change_list.html"
    change_list_form = ConstanceForm

    def __init__(self, model, admin_site):
        model._meta.concrete_model = Config
        super().__init__(model, admin_site)

    def get_urls(self):
        info = f"{self.model._meta.app_label}_{self.model._meta.module_name}"
        return [
            path("", self.admin_site.admin_view(self.changelist_view), name=f"{info}_changelist"),
            path("", self.admin_site.admin_view(self.changelist_view), name=f"{info}_add"),
            # Redirect <object_id>/change/ to the changelist so that "Recent actions" links in the admin index
            # point somewhere useful.  The relative "../../" resolves to the constance changelist because the
            # full path is <app>/<model>/<object_id>/change/ and two levels up lands on <app>/<model>/.
            path(
                "<path:object_id>/change/",
                self.admin_site.admin_view(lambda request, object_id: HttpResponseRedirect("../../")),
                name=f"{info}_change",
            ),
            path("history/", self.admin_site.admin_view(self.history_view), name=f"{info}_history"),
        ]

    def get_config_value(self, name, options, form, initial):
        default, help_text = options[0], options[1]
        field_type = None
        if len(options) == 3:
            field_type = options[2]
        # First try to load the value from the actual backend
        value = initial.get(name)
        # Then if the returned value is None, get the default
        if value is None:
            value = getattr(config, name)

        form_field = form[name]
        config_value = {
            "name": name,
            "default": localize(default),
            "raw_default": default,
            "help_text": _(help_text),
            "value": localize(value),
            "modified": localize(value) != localize(default),
            "form_field": form_field,
            "is_date": isinstance(default, date),
            "is_datetime": isinstance(default, datetime),
            "is_checkbox": isinstance(form_field.field.widget, forms.CheckboxInput),
            "is_multi_select": isinstance(form_field.field.widget, forms.SelectMultiple | forms.CheckboxSelectMultiple),
            "is_file": isinstance(form_field.field.widget, forms.FileInput),
        }
        if field_type and field_type in settings.ADDITIONAL_FIELDS:
            serialized_default = form[name].field.prepare_value(default)
            config_value["default"] = serialized_default
            config_value["raw_default"] = serialized_default
            config_value["value"] = form[name].field.prepare_value(value)

        if config_value["is_multi_select"]:
            raw_def = config_value["raw_default"]
            if isinstance(raw_def, list | tuple | set):
                default_list = list(raw_def)
            elif raw_def is None:
                default_list = []
            else:
                default_list = [raw_def]
            config_value["json_default"] = json.dumps(default_list)

        return config_value

    def get_changelist_form(self, request):
        """Returns a Form class for use in the changelist_view."""
        # Defaults to self.change_list_form in order to preserve backward
        # compatibility
        return self.change_list_form

    @csrf_protect_m
    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        initial = get_values()
        form_cls = self.get_changelist_form(request)
        form = form_cls(initial=initial, request=request)
        if request.method == "POST" and request.user.has_perm("constance.change_config"):
            form = form_cls(data=request.POST, files=request.FILES, initial=initial, request=request)
            if form.is_valid():
                changed_fields = form.save()
                if changed_fields:
                    self._log_config_change(request, changed_fields)
                messages.add_message(request, messages.SUCCESS, _("Live settings updated successfully."))
                return HttpResponseRedirect(".")
            messages.add_message(request, messages.ERROR, _("Failed to update live settings."))
        context = {
            **self.admin_site.each_context(request),
            **(extra_context or {}),
            "config_values": [],
            "title": self.model._meta.app_config.verbose_name,
            "app_label": "constance",
            "opts": self.model._meta,
            "form": form,
            "media": self.media + form.media,
            "icon_type": "svg",
            "django_version": get_version(),
        }
        for name, options in settings.CONFIG.items():
            context["config_values"].append(self.get_config_value(name, options, form, initial))

        if settings.CONFIG_FIELDSETS:
            if isinstance(settings.CONFIG_FIELDSETS, dict):
                fieldset_items = settings.CONFIG_FIELDSETS.items()
            else:
                fieldset_items = settings.CONFIG_FIELDSETS

            context["fieldsets"] = []
            for fieldset_title, fieldset_data in fieldset_items:
                if isinstance(fieldset_data, dict):
                    fields_list = fieldset_data["fields"]
                    collapse = fieldset_data.get("collapse", False)
                else:
                    fields_list = fieldset_data
                    collapse = False

                absent_fields = [field for field in fields_list if field not in settings.CONFIG]
                if any(absent_fields):
                    raise ValueError(
                        "CONSTANCE_CONFIG_FIELDSETS contains field(s) that does not exist(s): {}".format(
                            ", ".join(absent_fields)
                        )
                    )

                config_values = []

                for name in fields_list:
                    options = settings.CONFIG.get(name)
                    if options:
                        config_values.append(self.get_config_value(name, options, form, initial))
                fieldset_context = {"title": fieldset_title, "config_values": config_values}

                if collapse:
                    fieldset_context["collapse"] = True
                context["fieldsets"].append(fieldset_context)
            if not isinstance(settings.CONFIG_FIELDSETS, OrderedDict | tuple):
                context["fieldsets"].sort(key=itemgetter("title"))

        if not isinstance(settings.CONFIG, OrderedDict):
            context["config_values"].sort(key=itemgetter("name"))
        request.current_app = self.admin_site.name
        return TemplateResponse(request, self.change_list_template, context)

    def history_view(self, request, object_id=None, extra_context=None):
        """Display the change history for constance config values."""
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        ct = ContentType.objects.get_for_model(self.model)
        action_list = (
            LogEntry.objects.filter(
                content_type=ct,
                object_id="Config",
            )
            .select_related("user", "content_type")
            .order_by("-action_time")
        )

        paginator = self.get_paginator(request, action_list, 100)
        page_number = request.GET.get(PAGE_VAR, 1)
        page_obj = paginator.get_page(page_number)
        page_range = paginator.get_elided_page_range(page_obj.number)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Change history: %s") % self.model._meta.verbose_name_plural.capitalize(),
            "action_list": page_obj,
            "page_range": page_range,
            "page_var": PAGE_VAR,
            "pagination_required": paginator.count > 100,
            "opts": self.model._meta,
            "app_label": "constance",
            **(extra_context or {}),
        }

        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/constance/config_history.html",
            context,
        )

    def _log_config_change(self, request, changed_fields):
        """
        Create a Django admin LogEntry recording which config fields were changed.

        Uses the standard Django JSON change_message format so that
        LogEntry.get_change_message() can interpret it correctly.
        """
        ct = ContentType.objects.get_for_model(self.model)
        change_message = json.dumps([{"changed": {"fields": changed_fields}}])
        LogEntry.objects.create(
            user_id=request.user.pk,
            content_type_id=ct.pk,
            object_id="Config",
            object_repr="Config",
            action_flag=CHANGE,
            change_message=change_message,
        )

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_delete_permission(self, *args, **kwargs):
        return False

    def has_view_permission(self, request, obj=None):
        if settings.SUPERUSER_ONLY:
            return request.user.is_superuser
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if settings.SUPERUSER_ONLY:
            return request.user.is_superuser
        return super().has_change_permission(request, obj)


class Config:
    class Meta:
        app_label = "constance"
        object_name = "Config"
        concrete_model = None
        model_name = module_name = "config"
        verbose_name_plural = _("config")
        abstract = False
        swapped = False
        is_composite_pk = False

        def get_ordered_objects(self):
            return False

        def get_change_permission(self):
            return f"change_{self.model_name}"

        @property
        def app_config(self):
            return apps.get_app_config(self.app_label)

        @property
        def label(self):
            return f"{self.app_label}.{self.object_name}"

        @property
        def label_lower(self):
            return f"{self.app_label}.{self.model_name}"

    _meta = Meta()


admin.site.register([Config], ConstanceAdmin)
