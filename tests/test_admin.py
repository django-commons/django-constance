import json
from datetime import datetime
from unittest import mock

from django.contrib import admin
from django.contrib.admin.models import CHANGE
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.defaultfilters import linebreaksbr
from django.test import RequestFactory
from django.test import TestCase
from django.urls import resolve
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from constance import settings
from constance.admin import Config
from constance.forms import ConstanceForm
from constance.utils import get_values


class TestAdmin(TestCase):
    model = Config

    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        self.superuser = User.objects.create_superuser("admin", "nimda", "a@a.cz")
        self.normaluser = User.objects.create_user("normal", "nimda", "b@b.cz")
        self.normaluser.is_staff = True
        self.normaluser.save()
        self.options = admin.site._registry[self.model]
        # Clear ContentType cache to avoid stale content_type_id references
        # across tests wrapped in transactions.
        ContentType.objects.clear_cache()

    def test_changelist(self):
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        self.assertEqual(response.status_code, 200)

    def test_custom_auth(self):
        settings.SUPERUSER_ONLY = False
        self.client.login(username="normal", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.normaluser
        self.assertRaises(PermissionDenied, self.options.changelist_view, request, {})
        self.assertFalse(request.user.has_perm("constance.change_config"))

        # reload user to reset permission cache
        request = self.rf.get("/admin/constance/config/")
        request.user = User.objects.get(pk=self.normaluser.pk)

        request.user.user_permissions.add(Permission.objects.get(codename="change_config"))
        self.assertTrue(request.user.has_perm("constance.change_config"))

        response = self.options.changelist_view(request, {})
        self.assertEqual(response.status_code, 200)

    def test_linebreaks(self):
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        self.assertContains(response, "LINEBREAK_VALUE")
        self.assertContains(response, linebreaksbr("eggs\neggs"))

    @mock.patch(
        "constance.settings.CONFIG_FIELDSETS",
        {
            "Numbers": ("INT_VALUE",),
            "Text": ("STRING_VALUE",),
        },
    )
    def test_fieldset_headers(self):
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        self.assertContains(response, "Numbers</h2>")
        self.assertContains(response, "Text</h2>")

    @mock.patch(
        "constance.settings.CONFIG_FIELDSETS",
        (
            ("Numbers", ("INT_VALUE",)),
            ("Text", ("STRING_VALUE",)),
        ),
    )
    def test_fieldset_tuple(self):
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        self.assertContains(response, "Numbers</h2>")
        self.assertContains(response, "Text</h2>")

    @mock.patch(
        "constance.settings.CONFIG_FIELDSETS",
        {
            "Numbers": {
                "fields": (
                    "INT_VALUE",
                    "DECIMAL_VALUE",
                ),
                "collapse": True,
            },
            "Text": {
                "fields": (
                    "STRING_VALUE",
                    "LINEBREAK_VALUE",
                ),
                "collapse": True,
            },
        },
    )
    def test_collapsed_fieldsets(self):
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        self.assertContains(response, "module collapse")

    @mock.patch("constance.settings.CONFIG_FIELDSETS", {"FieldSetOne": ("INT_VALUE",)})
    @mock.patch(
        "constance.settings.CONFIG",
        {
            "INT_VALUE": (1, "some int"),
        },
    )
    @mock.patch("constance.settings.IGNORE_ADMIN_VERSION_CHECK", True)
    @mock.patch("constance.forms.ConstanceForm.save", lambda _: [])
    @mock.patch("constance.forms.ConstanceForm.is_valid", lambda _: True)
    def test_submit(self):
        """
        Test that submitting the admin page results in an http redirect when
        everything is in order.
        """
        initial_value = {"INT_VALUE": settings.CONFIG["INT_VALUE"][0]}

        self.client.login(username="admin", password="nimda")

        request = self.rf.post(
            "/admin/constance/config/",
            data={
                **initial_value,
                "version": "123",
            },
        )

        request.user = self.superuser
        request._dont_enforce_csrf_checks = True

        with (
            mock.patch("django.contrib.messages.add_message") as mock_message,
            mock.patch.object(ConstanceForm, "__init__", **initial_value, return_value=None) as mock_form,
        ):
            response = self.options.changelist_view(request, {})
            mock_form.assert_called_with(data=request.POST, files=request.FILES, initial=initial_value, request=request)
            mock_message.assert_called_with(request, 25, _("Live settings updated successfully."))

        self.assertIsInstance(response, HttpResponseRedirect)

    @mock.patch("constance.settings.CONFIG_FIELDSETS", {"FieldSetOne": ("MULTILINE",)})
    @mock.patch(
        "constance.settings.CONFIG",
        {
            "MULTILINE": ("Hello\nWorld", "multiline value"),
        },
    )
    @mock.patch("constance.settings.IGNORE_ADMIN_VERSION_CHECK", True)
    def test_newlines_normalization(self):
        self.client.login(username="admin", password="nimda")
        request = self.rf.post(
            "/admin/constance/config/",
            data={
                "MULTILINE": "Hello\r\nWorld",
                "version": "123",
            },
        )
        request.user = self.superuser
        request._dont_enforce_csrf_checks = True
        with mock.patch("django.contrib.messages.add_message"):
            response = self.options.changelist_view(request, {})
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(get_values()["MULTILINE"], "Hello\nWorld")

    @mock.patch(
        "constance.settings.CONFIG",
        {
            "DATETIME_VALUE": (datetime(2019, 8, 7, 18, 40, 0), "some naive datetime"),
        },
    )
    @mock.patch("constance.settings.IGNORE_ADMIN_VERSION_CHECK", True)
    @mock.patch("tests.redis_mockup.Connection.set", mock.MagicMock())
    def test_submit_aware_datetime(self):
        """
        Test that submitting the admin page results in an http redirect when
        everything is in order.
        """
        request = self.rf.post(
            "/admin/constance/config/",
            data={
                "DATETIME_VALUE_0": "2019-08-07",
                "DATETIME_VALUE_1": "19:17:01",
                "version": "123",
            },
        )
        request.user = self.superuser
        request._dont_enforce_csrf_checks = True
        with mock.patch("django.contrib.messages.add_message"):
            response = self.options.changelist_view(request, {})
        self.assertIsInstance(response, HttpResponseRedirect)

    @mock.patch(
        "constance.settings.CONFIG_FIELDSETS",
        {
            "Numbers": ("INT_VALUE",),
            "Text": ("STRING_VALUE",),
        },
    )
    def test_inconsistent_fieldset_submit(self):
        """
        Test that the admin page warns users if the CONFIG_FIELDSETS setting
        doesn't account for every field in CONFIG.
        """
        self.client.login(username="admin", password="nimda")
        request = self.rf.post("/admin/constance/config/", data=None)
        request.user = self.superuser
        request._dont_enforce_csrf_checks = True
        with mock.patch("django.contrib.messages.add_message"):
            response = self.options.changelist_view(request, {})
        self.assertContains(response, "is missing field(s)")

    @mock.patch(
        "constance.settings.CONFIG_FIELDSETS",
        {
            "Fieldsets": (
                "STRING_VALUE",
                "INT_VALUE",
            ),
        },
    )
    def test_fieldset_ordering_1(self):
        """Ordering of inner list should be preserved."""
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        response.render()
        content_str = response.content.decode()
        self.assertGreater(content_str.find("INT_VALUE"), content_str.find("STRING_VALUE"))

    @mock.patch(
        "constance.settings.CONFIG_FIELDSETS",
        {
            "Fieldsets": (
                "INT_VALUE",
                "STRING_VALUE",
            ),
        },
    )
    def test_fieldset_ordering_2(self):
        """Ordering of inner list should be preserved."""
        self.client.login(username="admin", password="nimda")
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request, {})
        response.render()
        content_str = response.content.decode()
        self.assertGreater(content_str.find("STRING_VALUE"), content_str.find("INT_VALUE"))

    @mock.patch(
        "constance.settings.ADDITIONAL_FIELDS",
        {
            "language_select": [
                "django.forms.fields.TypedMultipleChoiceField",
                {
                    "widget": "django.forms.CheckboxSelectMultiple",
                    "choices": (("en", "English"), ("de", "German"), ("fr", "French")),
                    "coerce": str,
                },
            ],
        },
    )
    @mock.patch(
        "constance.settings.CONFIG",
        {
            "LANGUAGES": (["en", "de"], "Supported languages", "language_select"),
        },
    )
    def test_reset_to_default_multi_select(self):
        """
        Test that multi-select config values render with data-field-type='multi-select'
        and a JSON-encoded data-default attribute.
        """
        # Re-parse additional fields so the mock is picked up by the form
        from constance.forms import FIELDS
        from constance.forms import parse_additional_fields

        FIELDS.update(
            parse_additional_fields(
                {
                    "language_select": [
                        "django.forms.fields.TypedMultipleChoiceField",
                        {
                            "widget": "django.forms.CheckboxSelectMultiple",
                            "choices": (("en", "English"), ("de", "German"), ("fr", "French")),
                            "coerce": str,
                        },
                    ]
                }
            )
        )
        try:
            self.client.login(username="admin", password="nimda")
            request = self.rf.get("/admin/constance/config/")
            request.user = self.superuser
            response = self.options.changelist_view(request, {})
            response.render()
            content = response.content.decode()

            self.assertIn('data-field-type="multi-select"', content)
            self.assertIn('data-default="[&quot;en&quot;, &quot;de&quot;]"', content)
        finally:
            # Clean up FIELDS to avoid leaking into other tests
            FIELDS.pop("language_select", None)

    @mock.patch(
        "constance.settings.ADDITIONAL_FIELDS",
        {
            "language_select": [
                "django.forms.fields.TypedMultipleChoiceField",
                {
                    "widget": "django.forms.CheckboxSelectMultiple",
                    "choices": (("en", "English"), ("de", "German"), ("fr", "French")),
                    "coerce": str,
                },
            ],
        },
    )
    @mock.patch(
        "constance.settings.CONFIG",
        {
            "LANGUAGES": (("en", "de"), "Supported languages", "language_select"),
        },
    )
    def test_reset_to_default_multi_select_tuple(self):
        """
        Test that multi-select config values with a tuple default serialize
        correctly to a flat JSON list.
        """
        from constance.forms import FIELDS
        from constance.forms import parse_additional_fields

        FIELDS.update(
            parse_additional_fields(
                {
                    "language_select": [
                        "django.forms.fields.TypedMultipleChoiceField",
                        {
                            "widget": "django.forms.CheckboxSelectMultiple",
                            "choices": (("en", "English"), ("de", "German"), ("fr", "French")),
                            "coerce": str,
                        },
                    ]
                }
            )
        )
        try:
            self.client.login(username="admin", password="nimda")
            request = self.rf.get("/admin/constance/config/")
            request.user = self.superuser
            response = self.options.changelist_view(request, {})
            response.render()
            content = response.content.decode()

            self.assertIn('data-field-type="multi-select"', content)
            self.assertIn('data-default="[&quot;en&quot;, &quot;de&quot;]"', content)
        finally:
            FIELDS.pop("language_select", None)

    @mock.patch("constance.settings.CONFIG_FIELDSETS", {"FieldSetOne": ("INT_VALUE", "STRING_VALUE")})
    @mock.patch(
        "constance.settings.CONFIG",
        {
            "INT_VALUE": (1, "some int"),
            "STRING_VALUE": ("Hello world", "greetings"),
        },
    )
    @mock.patch("constance.settings.IGNORE_ADMIN_VERSION_CHECK", True)
    @mock.patch("constance.forms.ConstanceForm.save", lambda _: ["INT_VALUE"])
    @mock.patch("constance.forms.ConstanceForm.is_valid", lambda _: True)
    def test_log_entry_created_on_change(self):
        """Test that a valid LogEntry is created when config values are changed."""
        request = self.rf.post(
            "/admin/constance/config/",
            data={
                "INT_VALUE": "42",
                "STRING_VALUE": "Hello world",
                "version": "123",
            },
        )
        request.user = self.superuser
        request._dont_enforce_csrf_checks = True

        with mock.patch("django.contrib.messages.add_message"):
            response = self.options.changelist_view(request, {})

        self.assertIsInstance(response, HttpResponseRedirect)
        log_entry = LogEntry.objects.latest("pk")
        self.assertEqual(log_entry.user, self.superuser)
        self.assertEqual(log_entry.action_flag, CHANGE)
        self.assertEqual(log_entry.object_repr, "Config")
        # Verify change_message uses Django's standard JSON format
        # so that get_change_message() can render it correctly.
        self.assertEqual(
            log_entry.get_change_message(),
            "Changed INT_VALUE.",
        )

    @mock.patch("constance.settings.CONFIG_FIELDSETS", {"FieldSetOne": ("INT_VALUE",)})
    @mock.patch(
        "constance.settings.CONFIG",
        {
            "INT_VALUE": (1, "some int"),
        },
    )
    @mock.patch("constance.settings.IGNORE_ADMIN_VERSION_CHECK", True)
    @mock.patch("constance.forms.ConstanceForm.save", lambda _: [])
    @mock.patch("constance.forms.ConstanceForm.is_valid", lambda _: True)
    def test_no_log_entry_when_no_changes(self):
        """Test that no LogEntry is created when the form is saved without any changes."""
        initial_count = LogEntry.objects.count()
        request = self.rf.post(
            "/admin/constance/config/",
            data={
                "INT_VALUE": "1",
                "version": "123",
            },
        )
        request.user = self.superuser
        request._dont_enforce_csrf_checks = True

        with mock.patch("django.contrib.messages.add_message"):
            response = self.options.changelist_view(request, {})

        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(LogEntry.objects.count(), initial_count)

    def test_history_view(self):
        """Test that the history view renders and shows LogEntry records."""
        ct = ContentType.objects.get_for_model(self.model)
        LogEntry.objects.create(
            user_id=self.superuser.pk,
            content_type_id=ct.pk,
            object_id="Config",
            object_repr="Config",
            action_flag=CHANGE,
            change_message=json.dumps([{"changed": {"fields": ["INT_VALUE"]}}]),
        )

        request = self.rf.get("/admin/constance/config/history/")
        request.user = self.superuser
        response = self.options.history_view(request)
        self.assertEqual(response.status_code, 200)
        response.render()
        content = response.content.decode()
        self.assertIn("INT_VALUE", content)
        self.assertIn("History", content)

    def test_history_view_fetches_users_with_entries(self):
        """Test that the history view loads each entry's user in the same query."""
        ct = ContentType.objects.get_for_model(self.model)
        editor = User.objects.create_user("editor", "editor@example.com", "editor")
        for user in (self.superuser, editor):
            LogEntry.objects.create(
                user_id=user.pk,
                content_type_id=ct.pk,
                object_id="Config",
                object_repr="Config",
                action_flag=CHANGE,
                change_message=json.dumps([{"changed": {"fields": ["INT_VALUE"]}}]),
            )

        request = self.rf.get("/admin/constance/config/history/")
        request.user = self.superuser
        response = self.options.history_view(request)
        entries = list(response.context_data["action_list"])
        with self.assertNumQueries(0):
            usernames = {entry.user.get_username() for entry in entries}
        self.assertEqual(usernames, {self.superuser.get_username(), "editor"})

    def test_history_view_empty(self):
        """Test that the history view renders correctly with no entries."""
        request = self.rf.get("/admin/constance/config/history/")
        request.user = self.superuser
        response = self.options.history_view(request)
        self.assertEqual(response.status_code, 200)
        response.render()
        content = response.content.decode()
        self.assertIn("doesn't have a change history", content)

    def test_history_view_permission_denied(self):
        """Test that the history view denies access to users without permission."""
        unprivileged = User.objects.create_user("noperm", "noperm", "c@c.cz")
        request = self.rf.get("/admin/constance/config/history/")
        request.user = unprivileged
        with self.assertRaises(PermissionDenied):
            self.options.history_view(request)

    def test_changelist_has_history_link(self):
        """Test that the changelist page contains a link to the history view."""
        request = self.rf.get("/admin/constance/config/")
        request.user = self.superuser
        response = self.options.changelist_view(request)
        response.render()
        content = response.content.decode()
        history_url = reverse("admin:constance_config_history")
        self.assertIn(f'href="{history_url}"', content)
        self.assertIn("History", content)

    def test_change_url_redirects_to_changelist(self):
        """Test that the change URL (used by 'Recent actions') redirects to the changelist."""
        url = reverse("admin:constance_config_change", args=["Config"])
        self.assertIn("Config/change/", url)
        request = self.rf.get(url)
        request.user = self.superuser

        # The change URL is a simple lambda redirect, so invoke it via URL resolution.
        match = resolve(url)
        response = match.func(request, object_id="Config")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "../../")

    def test_labels(self):
        self.assertEqual(type(self.model._meta.label), str)
        self.assertEqual(type(self.model._meta.label_lower), str)
