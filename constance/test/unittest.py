from functools import wraps

from asgiref.sync import iscoroutinefunction
from asgiref.sync import sync_to_async
from django import VERSION as DJANGO_VERSION
from django.test import SimpleTestCase
from django.test.utils import override_settings

from constance import config

__all__ = ("override_config",)


class override_config(override_settings):
    """
    Decorator to modify constance setting for TestCase.

    Based on django.test.utils.override_settings.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.original_values = {}

    def __call__(self, test_func):
        """Modify the decorated function to override config values."""
        if isinstance(test_func, type):
            if not issubclass(test_func, SimpleTestCase):
                raise Exception("Only subclasses of Django SimpleTestCase can be decorated with override_config")
            return self.modify_test_case(test_func)

        if iscoroutinefunction(test_func):

            @wraps(test_func)
            async def inner(*args, **kwargs):
                try:
                    await sync_to_async(self.enable, thread_sensitive=True)()
                    return await test_func(*args, **kwargs)
                finally:
                    await sync_to_async(self.disable, thread_sensitive=True)()

        else:

            @wraps(test_func)
            def inner(*args, **kwargs):
                with self:
                    return test_func(*args, **kwargs)

        return inner

    def modify_test_case(self, test_case):
        """
        Override the config by modifying TestCase methods.

        This method follows the Django <= 1.6 method of overriding the
        _pre_setup and _post_teardown hooks rather than modifying the TestCase
        itself.
        """
        original_pre_setup = test_case._pre_setup
        original_post_teardown = test_case._post_teardown

        if DJANGO_VERSION < (5, 2):

            def _pre_setup(inner_self):
                self.enable()
                original_pre_setup(inner_self)

        else:

            @classmethod
            def _pre_setup(cls):
                # NOTE: Django 5.2 turned this as a classmethod
                # https://github.com/django/django/pull/18514/files
                self.enable()
                original_pre_setup()

        def _post_teardown(inner_self):
            original_post_teardown(inner_self)
            self.disable()

        test_case._pre_setup = _pre_setup
        test_case._post_teardown = _post_teardown

        return test_case

    def enable(self):
        """Store original config values and set overridden values."""
        # Store the original values to an instance variable
        for config_key in self.options:
            self.original_values[config_key] = getattr(config, config_key)

        # Update config with the overridden values
        self.unpack_values(self.options)

    def disable(self):
        """Set original values to the config."""
        self.unpack_values(self.original_values)

    @staticmethod
    def unpack_values(options):
        """Unpack values from the given dict to config."""
        for name, value in options.items():
            setattr(config, name, value)
