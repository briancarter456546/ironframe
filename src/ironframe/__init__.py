"""
Iron Frame - Infrastructure reliability layer for LLM-powered systems.

Core promise: reliable, trustworthy, accurate, diligent.
Sits between raw LLMs and domain applications. Handles hallucinations,
reasoning errors, context drift, bias, and incomplete process execution.

Iron Frame is NOT domain logic. It is infrastructure.
"""

__version__ = "0.1.1"
__author__ = "Brian Carter"

from ironframe.config_v1_0 import IronFrameConfig
