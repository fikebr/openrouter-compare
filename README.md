# OpenRouter Compare

Compare responses from multiple AI models using the same prompt. The script sends requests in parallel through OpenRouter and saves each response with its token usage, request duration, and reported cost. Every run also produces a Markdown report with the prompt, a comparison table, and all responses.

Supports text prompts, a local image, optional web search, and extra text appended from the command line.

## Quick start

You need Git, [uv](https://docs.astral.sh/uv/), and an OpenRouter API key with access to the models you want to use. The script requires Python 3.10 or later; uv manages its environment and installs the declared dependencies.

These examples use Windows PowerShell. Run commands from the project folder.

```powershell
git clone https://github.com/fikebr/openrouter-compare.git
cd openrouter-compare
Copy-Item .env.example .env
notepad .env
```

Set your key in `.env`:

```dotenv
OPENROUTER_API_KEY=your-openrouter-key-here
```

Review the model IDs in `config.json`, then run:

```powershell
uv run .\compare_models.py .\prompts\python_automations.txt
```

No separate pip install or environment activation is needed. Requests use your OpenRouter account and can incur charges. `.env` and generated outputs are ignored by Git.

## Choose models

`config.json` contains the default model list:

```json
{
  "models": [
    "anthropic/claude-opus-5.5",
    "meta/muse-wonder",
    "openai/gpt-6-luna",
    "openai/gpt-6.1-sol"
  ]
}
```

Edit this list to use the exact OpenRouter IDs available to your account. The default config is loaded from beside the script. Select another config with `--config`, or override the model list for one run with `--models`:

```powershell
uv run .\compare_models.py .\prompts\get_rich.txt --config .\other-config.json
uv run .\compare_models.py .\prompts\get_rich.txt --models "openai/gpt-6-luna" "openai/gpt-6.1-sol"
```

## Included prompts

| File | Task |
|---|---|
| `prompts/python_automations.txt` | Suggest Python automation projects for a small business. |
| `prompts/get_rich.txt` | Answer “How do I get rich?” |
| `prompts/salmon_cocktail.txt` | Recommend a cocktail for salmon dinner using a liquor cabinet photo. |
| `prompts/political_news.txt` | Research yesterday's biggest U.S. political story and summarize it from left-wing, right-wing, and Canadian perspectives. |

Create additional UTF-8 text files and pass their paths as the first argument.

## Examples

### Include a photo

```powershell
uv run .\compare_models.py .\prompts\salmon_cocktail.txt --image .\liquor.jpeg
```

The script encodes the image and sends it with the text to every selected model. Choose models that support image input. Accepted file extensions are `.jpg`, `.jpeg`, `.png`, `.webp`, and `.gif`.

### Search the web and supply today's date

```powershell
$today = Get-Date -Format 'yyyy-MM-dd'
uv run .\compare_models.py .\prompts\political_news.txt --web-search --prompt-inject "Today's date is $today."
```

`--web-search` enables the `openrouter:web_search` server tool. OpenRouter handles search execution, and the model decides when to use it. Search can add charges and increase response time. See [OpenRouter's web search documentation](https://openrouter.ai/docs/guides/features/server-tools/web-search).

`--prompt-inject` appends the supplied text after a blank line. The combined prompt is sent to every model and included in the report. The original prompt file stays unchanged. The date above uses your computer's local date; use a literal date if you need a specific reference date.

### Adjust limits and output location

```powershell
uv run .\compare_models.py .\prompts\python_automations.txt --out .\results --max-tokens 8000 --timeout 600
```

## Command-line options

| Argument | Default | Purpose |
|---|---|---|
| `prompt` | Required | Path to a UTF-8 prompt text file. |
| `--models ID [ID ...]` | Config model list | Override the models for this run. |
| `--config PATH` | `config.json` beside the script | Read the model list from another JSON file. |
| `--image PATH` | None | Include one local image. |
| `--web-search` | Off | Enable OpenRouter's web search server tool. |
| `--prompt-inject TEXT` | None | Append text to the prompt. |
| `--out PATH` | `outputs` | Set the output root directory. |
| `--env PATH` | `.env` | Load a different environment file. |
| `--max-tokens N` | `4096` | Set the requested output token limit; must be positive. |
| `--timeout SECONDS` | `300` | Set the HTTP client timeout; must be positive. |

Explicit relative paths are resolved from your terminal's current directory. Existing environment variables take precedence over values loaded from the environment file.

For built-in help:

```powershell
uv run .\compare_models.py --help
```

## Output files and reports

Files are grouped by date and named using the run's start time, prompt filename without its extension, and model ID:

```text
outputs\YYYYMMDD\HHMMSS - promptfile - model.txt
outputs\YYYYMMDD\HHMMSS - promptfile - summary.md
```

For example:

```text
outputs\20261022\115100 - get_rich - anthropic_claude-opus-5.5.txt
outputs\20261022\115100 - get_rich - summary.md
```

Dates and times use the computer's local clock. Model and prompt names are sanitized for filenames, so `/` becomes `_`. Duplicate model filenames within a run receive numeric suffixes. If files already exist for the same prompt and second, the script stops to prevent overwriting them.

Each model's TXT file contains its requested and returned model IDs, response ID, status, request duration, input/output/total tokens, reported USD cost, finish reason, full usage data, and response or error message.

Each Markdown summary starts with the combined prompt, followed by a statistics table and every model's full response. Image runs also include the image filename. Links lead to the original TXT files. A summary includes only its own run, even when other runs share the date folder.

## Interpreting results

- Duration measures the complete HTTP request, including any server-side search work. It is not time to first token.
- Cost comes from OpenRouter's `usage.cost`; the script does not estimate missing costs. Missing values appear as `unavailable`, and reported zero costs remain zero.
- Output token counts can include reasoning tokens. Full usage data preserves provider-reported details.
- A finish reason of `length` indicates truncation at a token limit. Reasoning can consume the output token budget.
- Failed model requests are saved alongside successful responses and included in the summary. Requests are not automatically retried. A timeout can still incur charges.

Exit codes are `0` when all model requests succeed, `1` when any model request fails, and `2` for invalid CLI input.

## Tests

Run the mocked test suite without an API key or paid model requests:

```powershell
uv run --with httpx --with python-dotenv python -m unittest discover -s tests -v
```

Tests cover request payloads, image input, web search opt-in, prompt injection, configuration validation, parallel requests, error handling, usage reporting, output naming, and summary generation. They do not verify live model availability, credentials, search quality, or billing.
