import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import Studio
from engine import Engine, build_workflow, validate_options
from loras import hf_spec, import_loras, installed_loras, lora_folder, read_adapter, validate_selection


def fixture(path, marker=0):
    header = {"diffusion_model.blocks.0.self_attn.q.lora_A.weight": {"dtype": "F16", "shape": [1, 1536], "data_offsets": [0, 3072]},
              "diffusion_model.blocks.0.self_attn.q.lora_B.weight": {"dtype": "F16", "shape": [1536, 1], "data_offsets": [3072, 6144]}}
    encoded = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + bytes([marker]) * 6144)


class LoRATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_import_preserves_original_and_deduplicates(self):
        source = self.root / "style.safetensors"
        fixture(source)
        original = source.read_bytes()
        for _ in range(2):
            import_loras(self.root, [str(source)], lambda *x: None, threading.Event())
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(len(installed_loras(self.root)), 1)
        self.assertTrue(installed_loras(self.root)[0]["sha256"])

    def test_conflicting_names_preserve_both_files(self):
        source = self.root / "style.safetensors"
        fixture(source)
        import_loras(self.root, [str(source)], lambda *x: None, threading.Event())
        fixture(source, marker=1)
        import_loras(self.root, [str(source)], lambda *x: None, threading.Event())
        self.assertEqual(len(installed_loras(self.root)), 2)
        self.assertEqual((lora_folder(self.root) / "style.safetensors").read_bytes()[-1], 0)

    def test_invalid_and_truncated_files_rejected(self):
        source = self.root / "broken.safetensors"
        source.write_bytes(b"not a model")
        with self.assertRaises(ValueError): read_adapter(source)
        fixture(source)
        source.write_bytes(source.read_bytes()[:-5])
        with self.assertRaises(ValueError): read_adapter(source)

    def test_selection_validation_and_chained_model_clip(self):
        source = self.root / "style.safetensors"
        fixture(source)
        import_loras(self.root, [str(source)], lambda *x: None, threading.Event())
        selected = validate_selection(self.root, [{"name": source.name, "strength": .75}])
        options = validate_options({"prompt": "A lighthouse", "seed": 42, "loras": selected})
        graph = build_workflow(options, "test")
        self.assertEqual(graph["7"]["inputs"]["model"], ["20", 0])
        self.assertEqual(graph["4"]["inputs"]["clip"], ["20", 1])
        self.assertEqual(graph["20"]["inputs"]["strength_model"], .75)
        for value in ([{"name": "../missing.safetensors"}], [{"name": source.name, "strength": float("nan")}], selected * 2):
            with self.assertRaises(ValueError): validate_selection(self.root, value)

    def test_selection_preserves_existing_prompt_and_other_settings(self):
        source = self.root / "style.safetensors"
        fixture(source)
        import_loras(self.root, [str(source)], lambda *x: None, threading.Event())
        with patch("app.gpu_info", return_value={}): studio = Studio(self.root)
        studio.settings["options"]["prompt"] = "Keep my draft"
        studio.update_loras([{"name": source.name, "strength": .5}])
        self.assertEqual(studio.settings["options"]["prompt"], "Keep my draft")
        self.assertEqual(studio.settings["options"]["loras"][0]["strength"], .5)

    def test_hugging_face_file_link_normalization_and_pinning(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"sha": "abc123", "siblings": [{"rfilename": "sub/style.safetensors", "lfs": {"sha256": "a" * 64, "size": 1234}}]}).encode()
        with patch("loras.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            spec = hf_spec("https://huggingface.co/author/repo/blob/main/sub/style.safetensors?download=true")
        self.assertEqual(spec["url"], "https://huggingface.co/author/repo/resolve/abc123/sub/style.safetensors")
        self.assertEqual(spec["sha256"], "a" * 64)
        for link in ("https://example.org/file.safetensors", "https://huggingface.co/author/repo", "file:///test"):
            with self.assertRaises(ValueError): hf_spec(link)

    def test_concurrent_engine_close_terminates_only_once(self):
        engine = Engine(self.root, lambda *x: None)
        process = Mock()
        process.poll.return_value = None
        engine.process = process
        log = Mock()
        engine.log_handle = log
        workers = [threading.Thread(target=engine.stop) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        process.terminate.assert_called_once()
        log.close.assert_called_once()


if __name__ == "__main__": unittest.main()
