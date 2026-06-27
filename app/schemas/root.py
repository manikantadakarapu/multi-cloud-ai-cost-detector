"""Response model for the service root endpoint (``GET /``)."""

from pydantic import BaseModel, ConfigDict


class RootResponse(BaseModel):
    """Self-describing payload returned by the API root.

    Lets clients discover the service name, running version, and the
    canonical locations of documentation and health without guessing.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    status: str
    docs: str
    health: str
