import json
import hashlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import download_model


class CacheTests(unittest.TestCase):
    def test_interrupted_transfer_is_resumed_and_verified(self):
        content = b"complete-model-data"
        revision = "c" * 40
        metadata = {"sha": revision, "siblings": [{
            "rfilename": "model.safetensors", "size": len(content),
            "lfs": {"sha256": hashlib.sha256(content).hexdigest()},
        }]}
        first = io.BytesIO(content[:3])
        first.status = 200
        second = io.BytesIO(content[3:])
        second.status = 206
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(metadata).encode()), first, second]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(download_model, "build_opener", return_value=opener), patch.object(download_model.time, "sleep"):
                download_model.download("test/model", revision, Path(directory))
            self.assertEqual((Path(directory) / "model.safetensors").read_bytes(), content)
        self.assertEqual(opener.open.call_args_list[-1].args[0].get_header("Range"), "bytes=3-")

    def test_complete_part_is_recovered_without_redownload(self):
        content = b"complete-model-data"
        revision = "d" * 40
        metadata = {"sha": revision, "siblings": [{
            "rfilename": "model.safetensors", "size": len(content),
            "lfs": {"sha256": hashlib.sha256(content).hexdigest()},
        }]}
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(metadata).encode())]
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "model.safetensors.part").write_bytes(content)
            with patch.object(download_model, "build_opener", return_value=opener):
                download_model.download("test/model", revision, Path(directory))
            self.assertEqual((Path(directory) / "model.safetensors").read_bytes(), content)
        self.assertEqual(opener.open.call_count, 1)

    def test_restart_is_offline_and_corruption_is_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            revision = "a" * 40
            environment = {"MODEL_ID": "test/model", "MODEL_REVISION": revision, "MODEL_DIR": directory}

            def fetch(repo, revision, target):
                (target / "config.json").write_text("{}")
                (target / "model.safetensors").write_bytes(b"complete-model")

            with patch.dict(os.environ, environment):
                with patch.object(download_model, "download", side_effect=fetch) as first:
                    download_model.main()
                    self.assertEqual(first.call_count, 1)
                with patch.object(download_model, "download", side_effect=AssertionError("Network accessed")):
                    download_model.main()
                target = Path(directory) / revision
                (target / "model.safetensors").write_bytes(b"corrupt-model!")
                with patch.object(download_model, "download", side_effect=fetch) as repair:
                    download_model.main()
                    self.assertEqual(repair.call_count, 1)
                self.assertTrue(download_model.cached(target, "test/model", revision))

    def test_failed_download_does_not_mark_model_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            revision = "b" * 40
            environment = {"MODEL_ID": "test/model", "MODEL_REVISION": revision, "MODEL_DIR": directory}
            with patch.dict(os.environ, environment):
                with patch.object(download_model, "download", side_effect=OSError("Network interrupted")):
                    with self.assertRaises(OSError):
                        download_model.main()
            self.assertFalse((Path(directory) / revision / ".ready.json").exists())

    def test_redirect_does_not_leak_hf_token(self):
        request = download_model.Request("https://huggingface.co/file", headers={"Authorization": "Bearer private"})
        result = download_model.SafeRedirect().redirect_request(request, None, 302, "", {}, "https://cdn.example/file")
        self.assertFalse(result.has_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
