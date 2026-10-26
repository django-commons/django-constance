import asyncio
from unittest.mock import patch

from asgiref.sync import async_to_sync
from asgiref.sync import iscoroutinefunction
from django.test import TestCase
from django.test import TransactionTestCase

from constance import config
from constance.test import override_config


class OverrideConfigFunctionDecoratorTestCase(TestCase):
    """
    Test that the override_config decorator works correctly.

    Test usage of override_config on test method and as context manager.
    """

    def test_default_value_is_true(self):
        """Assert that the default value of config.BOOL_VALUE is True."""
        self.assertTrue(config.BOOL_VALUE)

    @override_config(BOOL_VALUE=False)
    def test_override_config_on_method_changes_config_value(self):
        """Assert that the method decorator changes config.BOOL_VALUE."""
        self.assertFalse(config.BOOL_VALUE)

    def test_override_config_as_context_manager_changes_config_value(self):
        """Assert that the context manager changes config.BOOL_VALUE."""
        with override_config(BOOL_VALUE=False):
            self.assertFalse(config.BOOL_VALUE)

        self.assertTrue(config.BOOL_VALUE)


@override_config(BOOL_VALUE=False)
class OverrideConfigClassDecoratorTestCase(TestCase):
    """Test that the override_config decorator works on classes."""

    def test_override_config_on_class_changes_config_value(self):
        """Assert that the class decorator changes config.BOOL_VALUE."""
        self.assertFalse(config.BOOL_VALUE)


class OverrideConfigAsyncDecoratorTestCase(TransactionTestCase):
    @override_config(BOOL_VALUE=False)
    async def test_override_config_on_async_method(self):
        self.assertFalse(await config.BOOL_VALUE)
        await asyncio.sleep(0)
        self.assertFalse(await config.BOOL_VALUE)

    def test_async_override_lasts_until_await_completes(self):
        @override_config(BOOL_VALUE=False)
        async def decorated():
            self.assertFalse(await config.BOOL_VALUE)
            await asyncio.sleep(0)
            self.assertFalse(await config.BOOL_VALUE)
            return "completed"

        self.assertTrue(iscoroutinefunction(decorated))
        self.assertEqual(async_to_sync(decorated)(), "completed")
        self.assertTrue(config.BOOL_VALUE)

    def test_async_override_restores_after_exception(self):
        @override_config(BOOL_VALUE=False)
        async def decorated():
            self.assertFalse(await config.BOOL_VALUE)
            await asyncio.sleep(0)
            raise ValueError("test failure")

        with self.assertRaisesMessage(ValueError, "test failure"):
            async_to_sync(decorated)()
        self.assertTrue(config.BOOL_VALUE)

    def test_async_override_with_database_backend(self):
        from constance import settings
        from constance.base import Config

        with patch.object(settings, "BACKEND", "constance.backends.database.DatabaseBackend"):
            database_config = Config()
        with patch("constance.test.unittest.config", database_config):

            @override_config(BOOL_VALUE=False)
            async def decorated():
                self.assertFalse(await database_config.BOOL_VALUE)
                await asyncio.sleep(0)
                self.assertFalse(await database_config.BOOL_VALUE)

            async_to_sync(decorated)()
        self.assertTrue(database_config.BOOL_VALUE)
