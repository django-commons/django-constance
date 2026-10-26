Testing
=======

Testing how your app behaves with different config values is achieved with the
:class:`override_config` class. This intentionally mirrors the use of Django's
:class:`~django.test.override_setting`.

.. py:class:: override_config(**kwargs)

    Replaces key-value pairs in the config.
    Use as decorator or context manager.

Usage
~~~~~

It can be used as a decorator at the :class:`~django.test.TestCase` level, the
method level and also as a
`context manager <https://peps.python.org/pep-0343/>`_.

.. code-block:: python

    from constance import config
    from constance.test import override_config

    from django.test import TestCase


    @override_config(YOUR_NAME="Arthur of Camelot")
    class ExampleTestCase(TestCase):

        def test_what_is_your_name(self):
            self.assertEqual(config.YOUR_NAME, "Arthur of Camelot")

        @override_config(YOUR_QUEST="To find the Holy Grail")
        def test_what_is_your_quest(self):
            self.assertEqual(config.YOUR_QUEST, "To find the Holy Grail")

        def test_what_is_your_favourite_color(self):
            with override_config(YOUR_FAVOURITE_COLOR="Blue?"):
                self.assertEqual(config.YOUR_FAVOURITE_COLOR, "Blue?")


The method decorator also supports ``async def`` tests. The overridden values
remain active until the awaited test completes, including when it raises an
exception.


Pytest usage
~~~~~~~~~~~~

Django-constance provides pytest plugin that adds marker
:class:`@pytest.mark.override_config()`. It handles config override for
module/class/function, and automatically revert any changes made to the
constance config values when test is completed.

.. py:function:: pytest.mark.override_config(**kwargs)

    Specify different config values for the marked tests in kwargs.

Module scope override

.. code-block:: python

    pytestmark = pytest.mark.override_config(API_URL="/awesome/url/")

    def test_api_url_is_awesome():
        ...

Class/function scope

.. code-block:: python

    from constance import config

    @pytest.mark.override_config(API_URL="/awesome/url/")
    class SomeClassTest:
        def test_is_awesome_url(self):
            assert config.API_URL == "/awesome/url/"

        @pytest.mark.override_config(API_URL="/another/awesome/url/")
        def test_another_awesome_url(self):
            assert config.API_URL == "/another/awesome/url/"

If you want to use override as a context manager or decorator, consider using

.. code-block:: python

    from constance.test.pytest import override_config

    def test_override_context_manager():
        with override_config(BOOL_VALUE=False):
            ...
    # or
    @override_config(BOOL_VALUE=False)
    def test_override_context_manager():
        ...

Pytest fixture as function or method parameter.

.. note:: No import needed as fixture is available globally.

.. code-block:: python

    def test_api_url_is_awesome(override_config):
        with override_config(API_URL="/awesome/url/"):
            ...

Any scope, auto-used fixture alternative can also be implemented like this

.. code-block:: python

    @pytest.fixture(scope='module', autouse=True)  # e.g. module scope
    def api_url(override_config):
        with override_config(API_URL="/awesome/url/"):
            yield


Memory backend
~~~~~~~~~~~~~~

If you don't want to rely on any external services such as Redis or database when
running your unittests you can select :class:`MemoryBackend` for a test Django settings file

.. code-block:: python

    CONSTANCE_BACKEND = 'constance.backends.memory.MemoryBackend'

It will provide simple thread-safe backend which will reset to default values after each
test run.
