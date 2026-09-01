"""Compatibility aliases for the former Azure-specific VLM client.

Production presentation code uses ``app.llm.configured_multimodal``.  These
aliases keep older extensions import-compatible without selecting a provider
or reading provider-specific environment variables.
"""

from app.llm.configured_multimodal import (
    ConfiguredMultimodalClient,
    ConfiguredMultimodalResult,
    parse_json_object,
)

AzureResponsesClient = ConfiguredMultimodalClient
AzureResponsesResult = ConfiguredMultimodalResult

__all__ = ["AzureResponsesClient", "AzureResponsesResult", "parse_json_object"]
