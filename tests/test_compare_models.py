import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare_models as app


class ModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_search_tool_opt_in(self):
        bodies = []
        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "News"}}]})
        with tempfile.TemporaryDirectory() as tmp:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                for index, enabled in enumerate((False, True), 1):
                    self.assertTrue(await app.run_model(client, "model", "News?", Path(tmp), index, 42, enabled))
        self.assertNotIn("tools", bodies[0])
        self.assertEqual(bodies[1]["tools"], [{"type": "openrouter:web_search"}])

    async def test_cli_image_payload_and_invalid_files(self):
        real_client = httpx.AsyncClient
        requests = []
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9X8AAAAASUVORK5CYII="
        )
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "Done"}}]})
        def client_factory(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prompt.txt").write_text("Suggest a cocktail")
            image = root / "cabinet.PNG"
            image.write_bytes(image_bytes)
            argv = ["compare_models.py", str(root / "prompt.txt"), "--models", "one", "two",
                    "--out", str(root / "outputs"), "--prompt-inject", "Dinner is tonight.",
                    "--image", str(image)]
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake"}), \
                    patch.object(sys, "argv", argv), \
                    patch.object(app.httpx, "AsyncClient", client_factory):
                self.assertEqual(await app.main(), 0)
                self.assertEqual(len(requests), 2)
                summary = next((root / "outputs").glob("*/summary.md")).read_text(encoding="utf-8")
                self.assertTrue(summary.startswith("Suggest a cocktail\n"))
                self.assertIn("Suggest a cocktail\n\nDinner is tonight.", summary)
                self.assertEqual((root / "prompt.txt").read_text(), "Suggest a cocktail")
                self.assertIn("Image supplied: cabinet.PNG", summary)
                self.assertNotIn("data:image", summary)
                for body in requests:
                    content = body["messages"][0]["content"]
                    self.assertEqual(content[0], {"type": "text", "text": "Suggest a cocktail\n\nDinner is tonight."})
                    self.assertEqual(content[1]["type"], "image_url")
                    prefix, encoded = content[1]["image_url"]["url"].split(",", 1)
                    self.assertEqual(prefix, "data:image/png;base64")
                    self.assertEqual(base64.b64decode(encoded), image_bytes)
                image.write_bytes(b"")
                for path in (image, root / "missing.jpg", root / "unsupported.txt"):
                    argv[-1] = str(path)
                    with self.assertRaises(SystemExit) as caught:
                        await app.main()
                    self.assertEqual(caught.exception.code, 2)
                self.assertEqual(len(requests), 2)

    async def run_case(self, handler, models=("vendor/model",)):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                headers={"Authorization": "Bearer fake-secret"},
            ) as client:
                statuses = await asyncio.gather(*[
                    app.run_model(client, model, "A prompt", folder, i, 42)
                    for i, model in enumerate(models, 1)
                ])
            return statuses, {p.name: p.read_text(encoding="utf-8") for p in folder.iterdir()}

    async def test_success_usage_and_request(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["messages"][0]["content"], "A prompt")
            self.assertEqual(body["max_tokens"], 42)
            self.assertEqual(request.headers["Authorization"], "Bearer fake-secret")
            return httpx.Response(200, json={
                "id": "test-123", "model": "vendor/model",
                "choices": [{"message": {"content": "Hello café"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                          "total_tokens": 30, "cost": 0.00123},
            })
        statuses, files = await self.run_case(handler)
        self.assertEqual(statuses, [True])
        text = files["01_vendor_model.txt"]
        for expected in ("Hello café", "Input tokens: 10", "Output tokens: 20",
                         "Total tokens: 30", "$0.0012300000", "seconds", "test-123"):
            self.assertIn(expected, text)

    async def test_zero_and_missing_cost(self):
        def handler(request):
            model = json.loads(request.content)["model"]
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"cost": 0} if model == "zero" else {},
            })
        statuses, files = await self.run_case(handler, ("zero", "missing"))
        self.assertEqual(statuses, [True, True])
        self.assertIn("$0.0000000000", files["01_zero.txt"])
        self.assertIn("unavailable", files["02_missing.txt"])

    async def test_http_failure_does_not_stop_other_models(self):
        def handler(request):
            if json.loads(request.content)["model"] == "bad":
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        statuses, files = await self.run_case(handler, ("bad", "good"))
        self.assertEqual(statuses, [False, True])
        self.assertIn("Status: ERROR", files["01_bad.txt"])
        self.assertIn("Status: OK", files["02_good.txt"])

    async def test_timeout_and_api_error(self):
        def handler(request):
            if json.loads(request.content)["model"] == "timeout":
                raise httpx.ReadTimeout("Timed out", request=request)
            return httpx.Response(200, json={"error": {"message": "fake-secret rejected"}})
        statuses, files = await self.run_case(handler, ("timeout", "api/error"))
        self.assertEqual(statuses, [False, False])
        self.assertIn("ReadTimeout", files["01_timeout.txt"])
        self.assertIn("[REDACTED]", files["02_api_error.txt"])
        self.assertNotIn("fake-secret", files["02_api_error.txt"])

    async def test_parallel_and_filename_collisions(self):
        count = 0
        ready = asyncio.Event()
        async def handler(request):
            nonlocal count
            count += 1
            if count == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=2)
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        statuses, files = await self.run_case(handler, ("a/b", "a:b"))
        self.assertEqual(statuses, [True, True])
        self.assertEqual(set(files), {"01_a_b.txt", "02_a_b.txt"})

    async def test_cli_env_utf8_bom_and_output(self):
        real_client = httpx.AsyncClient
        def handler(request):
            self.assertEqual(json.loads(request.content)["messages"][0]["content"], "Prompt café\n\nToday's date is 2026-10-22.")
            self.assertEqual(request.headers["Authorization"], "Bearer from-dotenv")
            return httpx.Response(200, json={"choices": [{"message": {"content": "Done"}}]})
        def client_factory(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prompt.txt").write_text("Prompt café", encoding="utf-8-sig")
            (root / ".env").write_text("OPENROUTER_API_KEY=from-dotenv\n")
            argv = ["compare_models.py", str(root / "prompt.txt"), "--env", str(root / ".env"),
                    "--out", str(root / "outputs"), "--models", "one", "two",
                    "--prompt-inject", "Today's date is 2026-10-22."]
            with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", argv), \
                    patch.object(app.httpx, "AsyncClient", client_factory):
                self.assertEqual(await app.main(), 0)
            self.assertEqual(len(list((root / "outputs").glob("*/*.txt"))), 2)
            summary = next((root / "outputs").glob("*/summary.md")).read_text(encoding="utf-8")
            self.assertTrue(summary.startswith("Prompt café\n"))
            self.assertIn("Prompt café\n\nToday's date is 2026-10-22.", summary)
            self.assertLess(summary.index("## Run statistics"), summary.index("## Responses"))
            self.assertIn("### one", summary)
            self.assertIn("### two", summary)
            self.assertEqual(summary.count("\nDone"), 2)

    async def test_summary_mixed_results_and_stats(self):
        def handler(request):
            model = json.loads(request.content)["model"]
            if model == "bad":
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "Full response café\n\nSecond paragraph"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "cost": 0},
            })
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                await asyncio.gather(*[
                    app.run_model(client, model, "A prompt", folder, i, 42)
                    for i, model in enumerate(("good", "bad"), 1)
                ])
            app.write_summary(folder, "A prompt")
            summary = (folder / "summary.md").read_text(encoding="utf-8")
            self.assertIn("| good | OK | 10 | 20 | 30 |", summary)
            self.assertIn("$0.0000000000", summary)
            self.assertIn("| bad | ERROR | unavailable | unavailable | unavailable |", summary)
            self.assertIn("Full response café\n\nSecond paragraph", summary)
            self.assertIn("HTTPStatusError", summary)

    async def test_cli_config_models_and_validation(self):
        real_client = httpx.AsyncClient
        requested = []
        def handler(request):
            requested.append(json.loads(request.content)["model"])
            return httpx.Response(200, json={"choices": [{"message": {"content": "Done"}}]})
        def client_factory(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.txt"
            prompt.write_text("Hello")
            config = root / "config.json"
            argv = ["compare_models.py", str(prompt), "--config", str(config),
                    "--out", str(root / "outputs")]
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake"}), \
                    patch.object(sys, "argv", argv), \
                    patch.object(app.httpx, "AsyncClient", client_factory):
                config.write_text('{"models": ["one", " two "]}')
                self.assertEqual(await app.main(), 0)
                self.assertEqual(requested, ["one", "two"])
                for invalid in ('{}', '{"models": []}', '{"models": [1]}',
                                '{"models": [" "]}', '{broken'):
                    config.write_text(invalid)
                    with self.assertRaises(SystemExit) as caught:
                        await app.main()
                    self.assertEqual(caught.exception.code, 2)
                config.unlink()
                with self.assertRaises(SystemExit) as caught:
                    await app.main()
                self.assertEqual(caught.exception.code, 2)
                argv.extend(["--models", "override"])
                self.assertEqual(await app.main(), 0)
                self.assertEqual(requested[-1], "override")

    async def test_cli_rejects_empty_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prompt.txt").write_text("  ")
            argv = ["compare_models.py", str(root / "prompt.txt"), "--models", "one",
                    "--env", str(root / "not-present.env")]
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake"}), \
                    patch.object(sys, "argv", argv):
                with self.assertRaises(SystemExit) as caught:
                    await app.main()
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
