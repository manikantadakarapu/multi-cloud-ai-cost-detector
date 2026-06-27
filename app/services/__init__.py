"""Service layer.

Services encapsulate business logic that does not belong in route handlers
or the data-access layer. Routes stay thin: they validate input, delegate to
a service, and translate the result into an HTTP response.
"""
