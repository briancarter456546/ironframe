"""Model Abstraction Layer - the only component that touches LLMs directly."""

from ironframe.mal.client_v1_0 import IronFrameClient
from ironframe.mal.response_v1_0 import IronFrameResponse


def get_client(**kwargs):
    """Convenience factory for IronFrameClient."""
    return IronFrameClient(**kwargs)
