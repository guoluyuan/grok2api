import base64
import hashlib
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


def _load_headers_module():
    logger_stub = types.SimpleNamespace(debug=lambda *args, **kwargs: None)
    sys.modules.setdefault("app", types.ModuleType("app"))
    sys.modules.setdefault("app.platform", types.ModuleType("app.platform"))
    sys.modules.setdefault("app.platform.logging", types.ModuleType("app.platform.logging"))
    sys.modules["app.platform.logging.logger"] = types.SimpleNamespace(logger=logger_stub)
    sys.modules.setdefault("app.platform.config", types.ModuleType("app.platform.config"))
    sys.modules["app.platform.config.snapshot"] = types.SimpleNamespace(get_config=lambda: None)
    sys.modules.setdefault("app.control", types.ModuleType("app.control"))
    sys.modules.setdefault("app.control.proxy", types.ModuleType("app.control.proxy"))
    sys.modules["app.control.proxy.models"] = types.SimpleNamespace(ProxyLease=object)
    sys.modules.setdefault("app.dataplane", types.ModuleType("app.dataplane"))
    sys.modules.setdefault("app.dataplane.proxy", types.ModuleType("app.dataplane.proxy"))
    sys.modules.setdefault("app.dataplane.proxy.adapters", types.ModuleType("app.dataplane.proxy.adapters"))
    sys.modules["app.dataplane.proxy.adapters.profile"] = types.SimpleNamespace(
        ProxyProfile=object,
        resolve_proxy_profile=lambda lease: None,
    )

    file_path = pathlib.Path(__file__).resolve().parents[1] / "app/dataplane/proxy/adapters/headers.py"
    spec = importlib.util.spec_from_file_location("test_headers_module", file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


headers = _load_headers_module()


class _DummyConfig:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def get_bool(self, key, default=False):
        if key == "features.dynamic_statsig":
            return self.enabled
        return default


def _decode_statsig(value: str) -> bytes:
    raw = base64.b64decode(value + "=" * (-len(value) % 4))
    key = raw[0]
    return bytes(byte if index == 0 else byte ^ key for index, byte in enumerate(raw))


class StatsigIdTests(unittest.TestCase):
    def test_dynamic_statsig_matches_current_frontend_shape(self):
        counter = 98852040
        path = "/rest/rate-limits"
        method = "POST"

        with patch.object(headers, "get_config", return_value=_DummyConfig()):
            with patch.object(headers.time, "time", return_value=headers.STATSIG_EPOCH + counter):
                with patch.object(headers.os, "urandom", return_value=b"\x7b"):
                    value = headers._statsig_id(path, method)

        body = _decode_statsig(value)
        expected_meta = base64.b64decode(headers.STATSIG_META_B64)
        expected_preimage = (
            f"{method}!{path}!{counter}"
            f"{headers.STATSIG_SUFFIX}{headers.STATSIG_FINGERPRINT}"
        )
        expected_digest = hashlib.sha256(expected_preimage.encode()).digest()[:16]

        self.assertEqual(len(body), 70)
        self.assertEqual(body[0], 0x7B)
        self.assertEqual(body[1:49], expected_meta)
        self.assertEqual(int.from_bytes(body[49:53], "little"), counter)
        self.assertEqual(body[53:69], expected_digest)
        self.assertEqual(body[69], headers.STATSIG_VERSION)

    def test_static_statsig_keeps_legacy_value_when_dynamic_disabled(self):
        with patch.object(headers, "get_config", return_value=_DummyConfig(False)):
            self.assertEqual(headers._statsig_id(), headers.STATIC_STATSIG_ID)


if __name__ == "__main__":
    unittest.main()
