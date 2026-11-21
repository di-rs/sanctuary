# Check whether Grafana tools fit a local assistant's first request

“Find the Boxie operations dashboard.” An operator monitoring Boxie, Sanctuary's
sandbox runtime, needs just Grafana's `search_dashboards` tool for that request.
If a private assistant sends every tool definition up front, its prompt can
exceed the model's context window before the first search. A proposed
Sanctuary CLI would show which tool menus leave room for a reply and still
offer dashboard search.

An OpenClaw user reported that setup passed on an 8,192-token local deployment.
The first ordinary message failed once the client included its instructions and
tools. MCPUsage already counts advertised tool definitions and can export them
for comparison. The deployment decision also depends on how the model formats
those definitions and how much room the operator reserves for the reply.
[OpenClaw first-request report](https://github.com/openclaw/openclaw/issues/200920)
and [MCPUsage's counting method](https://github.com/cameroncooke/MCPUsage#how-token-counting-works)

## A dashboard search with three tool menus

Sanctuary enables four read-only tool groups in Grafana's Model Context
Protocol (MCP) adapter. A local copy of the pinned 2.3.0 release supplied the
tool definitions through `tools/list`. For the question above, the trial set
a 4,096-token context window and reserved 512 tokens for the reply.
[Sanctuary's Grafana settings](../../packages/boxie/infra/mcp/start-grafana.sh)
and [Grafana adapter release](https://github.com/grafana/mcp-grafana/releases/tag/v2.3.0)

| Tool menu | Prompt tokens | Room after reserving the reply | Dashboard search |
| --- | ---: | ---: | --- |
| Empty menu | 36 | 3,548 spare | Missing |
| Search (2 tools) | 473 | 3,111 spare | Available |
| Search, data sources, dashboards and Prometheus (16 tools) | 4,576 | 992 over budget | Available |

To repeat the trial, use the adapter's `--enabled-tools search` setting for
the smaller menu and Sanctuary's settings for the larger one. Copy each tool's
`name` and `description` and use its `inputSchema` as `parameters` in a
`{"type": "function", "function": …}` entry. Use the question above as the
sole message with the `user` role.

With Transformers 4.57.1 and the Qwen2.5-1.5B-Instruct tokenizer, count the
IDs from `apply_chat_template` with the chosen `tools`, `tokenize=True` and
`add_generation_prompt=True`. Encoding the 16 function definitions alone as
compact JSON took 3,797 tokens. Qwen's template also formats the definitions
and adds instructions for calling the tools.
[Pinned Qwen chat template](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/989aa7980e4cf806f80c7fef2b1adb7bc71aa306/tokenizer_config.json)

## Try it on an adapter change

Start with a team whose developers review adapter changes on laptops outside
the inference network. The CLI would read the messages and tools their client
would send, including its system instructions, and apply the deployment's
tokenizer, chat template and limits locally. The review would show the case
name, the number of tokens spare or missing, and whether the required tool is
present. The request text would stay on the laptop.

For calibration, have the operator submit the three synthetic cases to their
private vLLM server's `/tokenize` endpoint with matching template settings.
It returns the prompt count and the configured context limit. Carry the local
check into the team's next adapter review if all three counts agree and the
search-only assistant finds `boxie-operations` in staging. If reviewers can
already make that decision with a saved `/tokenize` request, keep the three
cases as fixtures for their existing check.
[vLLM tokenizer protocol](https://docs.vllm.ai/en/v0.15.1/api/vllm/entrypoints/serve/tokenize/protocol/)
