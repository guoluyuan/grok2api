import importlib.util
import pathlib
import unittest


class ImageEditUrlResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = pathlib.Path(__file__).resolve().parents[1]
        cls.images_source = (cls.project / "app/products/openai/images.py").read_text(encoding="utf-8")

    def _load_helper_namespace(self):
        helper_source = self._source_between("def _absolutize_asset_url", "def _parse_image_index")
        assets = self._load_module("test_xai_assets", "app/dataplane/reverse/protocol/xai_assets.py")
        namespace = {
            "Any": object,
            "extract_streaming_response": lambda data: None,
            "extract_model_response_file_attachments": lambda data: [],
            "extract_model_response_urls": self._extract_model_response_urls,
            "resolve_download_url": assets.resolve_download_url,
            "resolve_asset_reference": assets.resolve_asset_reference,
        }
        exec(helper_source, namespace)
        return namespace

    def _load_module(self, name, relative_path):
        spec = importlib.util.spec_from_file_location(name, self.project / relative_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def _source_between(self, start_marker, end_marker):
        start = self.images_source.index(start_marker)
        end = self.images_source.index(end_marker, start)
        return self.images_source[start:end]

    def _extract_model_response_urls(self, data):
        response = data["result"]["response"]
        return response["modelResponse"].get("generatedImageUrls", [])

    def test_raw_stream_url_wins_over_asset_content_url(self):
        helpers = self._load_helper_namespace()
        result = helpers["_resolve_edit_final_url"](
            raw_url="users/u/generated/a/image.jpg",
            asset_id="a",
            user_id="u",
        )
        self.assertEqual(result, "https://assets.grok.com/users/u/generated/a/image.jpg")

    def test_asset_content_url_used_when_raw_url_absent(self):
        helpers = self._load_helper_namespace()
        result = helpers["_resolve_edit_final_url"](
            raw_url=None,
            asset_id="a",
            user_id="u",
        )
        self.assertEqual(result, "https://assets.grok.com/users/u/a/content")

    def test_model_response_url_overrides_earlier_asset_attachment(self):
        helpers = self._load_helper_namespace()
        final_urls = {0: "https://assets.grok.com/users/u/a/content"}
        obj = {
            "result": {
                "response": {
                    "modelResponse": {
                        "generatedImageUrls": ["users/u/generated/a/image.jpg"]
                    }
                }
            }
        }

        helpers["_collect_edit_results"](obj=obj, final_urls=final_urls, user_id="u")

        self.assertEqual(
            final_urls[0],
            "https://assets.grok.com/users/u/generated/a/image.jpg",
        )


if __name__ == "__main__":
    unittest.main()
