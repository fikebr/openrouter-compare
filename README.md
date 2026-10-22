# OpenRouter model comparison

Send a prompt from a UTF-8 text file to multiple text models in parallel.
Each model gets a separate TXT output containing its response, elapsed request
time, input/output/total tokens, reported USD cost, and finish reason.

Add `--image` to send a local JPEG, PNG, WebP, or GIF alongside the prompt:

```powershell
uv run .\compare_models.py .\prompt_salmon_cocktail.txt --image .\liquor_cabinet.jpg
```

The image is encoded and sent to every configured model. Choose models that
support image input. Without `--image`, the request contains only text.

## Windows PowerShell quick start

Requires uv. Extract this folder and open a terminal in it.

```powershell
Copy-Item .env.example .env
notepad .env
```

Set your OpenRouter key in `.env`. Put your prompt in `prompt.txt`.
Edit `config.json` beside the script and replace its placeholder model IDs with
the exact OpenRouter model IDs you want to compare:

```json
{
  "models": ["vendor/model-one", "vendor/model-two"]
}
```

Then run:

```powershell
uv run .\compare_models.py .\prompt.txt
```

Use `--prompt-inject` to append extra text to the prompt, separated by a blank
line. The combined prompt is sent to every model and included in `summary.md`;
the original prompt file is unchanged.

Add `--web-search` to enable OpenRouter's web search server tool. OpenRouter
handles tool execution; search can incur additional charges.

```powershell
uv run .\compare_models.py .\prompt_political_news.txt --web-search --prompt-inject "Today's date is 2026-10-22."
```

uv installs the dependencies declared in the script automatically. No manual
pip install, activation, or project initialization is needed.

Use `--config path\to\config.json` to select another config file. Relative config
paths are resolved from your terminal's current directory. `--models` overrides
the config's model list for a single run.

```powershell
uv run .\compare_models.py .\prompt.txt --models "vendor/model-one" "vendor/model-two" --out .\results --max-tokens 8000 --timeout 600
```

`--env path` selects another .env file. Default paths are relative to your
terminal's current directory. Existing environment variables take precedence
over .env values.

Each run creates a new timestamped subfolder under `outputs` (or `--out`).
It also creates `summary.md` in that folder, starting with the prompt, followed
by a table of model status, input/output/total tokens, time, and cost, then each
model's full response. Image runs include the image filename. Failed requests
are included with their error messages and any available statistics.
Model names are sanitized for Windows filenames and numbered to prevent
collisions. Failed requests write error files while the other requests continue.
Exit status is 1 if any model fails, otherwise 0; invalid CLI input exits 2.

Response time is full HTTP request duration, not time to first token. Cost is
OpenRouter's reported `usage.cost`, not an estimate; omitted values are marked
unavailable and zero-cost responses remain $0. Full usage is included for
reasoning/cached-token details when supplied. A finish reason of `length`
means output was truncated at a token limit. Reasoning may consume output tokens.
No automatic request retries are made. A timeout can still incur API charges.
Never commit your .env file.

## Tests (no API key or paid requests needed)

```powershell
uv run --with httpx --with python-dotenv python -m unittest discover -s tests -v
```

Tests simulate HTTP responses; they do not verify live credentials, model
availability, or actual billing. See TEST_RESULTS.txt for the packaged run.
