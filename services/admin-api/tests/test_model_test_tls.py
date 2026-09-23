from __future__ import annotations

import ssl
import urllib.error
from unittest import TestCase
from unittest.mock import patch

from app.services.model_test_tls import build_model_test_ssl_context, format_model_test_url_error


class ModelTestTlsTests(TestCase):
    def test_uses_certifi_bundle_by_default(self) -> None:
        sentinel = ssl.create_default_context()
        with (
            patch("app.services.model_test_tls.settings.model_test_insecure_skip_verify", False),
            patch("app.services.model_test_tls.settings.model_test_ca_bundle", ""),
            patch("app.services.model_test_tls.certifi.where", return_value="/certifi/ca.pem"),
            patch("app.services.model_test_tls.ssl.create_default_context", return_value=sentinel) as create_context,
        ):
            result = build_model_test_ssl_context()
        self.assertIs(result, sentinel)
        create_context.assert_called_once_with(cafile="/certifi/ca.pem")

    def test_custom_ca_bundle_takes_precedence(self) -> None:
        with (
            patch("app.services.model_test_tls.settings.model_test_insecure_skip_verify", False),
            patch("app.services.model_test_tls.settings.model_test_ca_bundle", "/private/company-ca.pem"),
            patch("app.services.model_test_tls.ssl.create_default_context") as create_context,
        ):
            build_model_test_ssl_context()
        create_context.assert_called_once_with(cafile="/private/company-ca.pem")

    def test_certificate_error_has_actionable_configuration_guidance(self) -> None:
        error = urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")
        message = format_model_test_url_error(error, service_name="模型服务")
        self.assertIn("ASKAI_ADMIN_MODEL_TEST_CA_BUNDLE", message)
        self.assertIn("certifi", message)
