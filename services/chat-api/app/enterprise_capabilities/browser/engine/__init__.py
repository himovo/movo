"""Browser runtime package.

Keep this package initializer free of implementation imports.  Browser
execution has multiple consumers (the native-CDP desktop path and ordinary
runtime services), so importing a lightweight submodule must never pull in an
optional browser engine as a side effect.
"""

__all__: list[str] = []
