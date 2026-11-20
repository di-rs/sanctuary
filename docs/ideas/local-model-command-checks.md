# Check command suggestions before switching local models

A support engineer asks a terminal assistant, “Which device IDs appear in
today's inventory and were absent yesterday?” Before switching the assistant
to a smaller local model, its maintainer could run a Sanctuary test pack and
see each model's suggested command alongside the expected and actual IDs.

## Catch a reversed comparison

Sanctuary's `commr` compares two sorted files. With `-13`, it hides lines
unique to the first file and lines shared by both. The remaining lines are
unique to the second file. Suppose yesterday's file contains `A17` and `B24`,
and today's contains `B24` and `C88`, one ID per line.
[commr options](../../buildins/commr/README.md#arguments-and-options)

| Arguments after `commr` | ID printed | Grade |
| --- | --- | --- |
| `-13 yesterday.txt today.txt` | `C88` | Pass |
| `-23 today.txt yesterday.txt` | `C88` | Pass |
| `-23 yesterday.txt today.txt` | `A17` | Fail |

In a local check, `commr` exited zero for all 16 combinations of column
switches and file order. When both files contained only `B24`, eight of those
choices produced the expected empty output. On the inventory above, just two
printed `C88`. The answer key used stdout bytes, stderr and exit status from
`LC_ALL=C /usr/bin/comm -13 yesterday.txt today.txt` on macOS. A third pair
used the package's existing inputs and expected output.
[commr reference cases](../../buildins/commr/tests/cases.toml)

## Deliver the check through Promptfoo

ShellGPT offers the person at the terminal a chance to review each suggested
command. A test pack would serve the maintainer choosing the model behind
such a feature. Westenfelder and colleagues studied this grading problem
using 600 manually checked request–command pairs for Bash. Their method
combined execution with a model's judgment of the outputs. For inventory
IDs, an exact comparison can tell the maintainer which line was wrong.
[ShellGPT's shell mode](https://github.com/TheR1D/shell_gpt#shell-commands)
and [the NAACL study](https://aclanthology.org/2025.naacl-long.555/)

Promptfoo can compare models served locally by Ollama and display a reason
from a Python assertion. Sanctuary would supply the requests, fixtures and
assertion in one versioned pack. Each model would receive the request,
filenames and `commr` option table, then return arguments as a JSON array
such as `["-13", "yesterday.txt", "today.txt"]`. The assertion would accept
any subset of `-1`, `-2` and `-3`, grouped or separate, followed by the two
fixture names once each in either order. It would pass those arguments
directly to a fixed `commr` executable and reject other replies before launch.
[Ollama provider](https://www.promptfoo.dev/docs/providers/ollama/)
and [Python assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/python/)

A local trial with Promptfoo 0.126.0's Echo provider replayed 19 fixed
replies. The grader accepted both commands that produced `C88` and a third spelling
with separate flags. It rejected the 14 wrong comparisons, an unknown
filename and a reply containing a whole shell command.
[Promptfoo Echo](https://www.promptfoo.dev/docs/providers/echo/)

## Decide whether to add a second command

Ask two teams to compare their current and candidate models with both
installed in Ollama on the same workstation. Give them six fresh requests,
two each for added, removed and shared IDs. With yesterday's file first,
the reference commands use `comm -13`, `comm -23` and `comm -12` respectively.
Keep the command guide, prompts and decoding settings fixed across models.
Run three uncached attempts per request. A reply earns one point if it passes
every file pair, for a score out of 18 per model. Teams evaluating on a
private network could use Promptfoo's offline settings with its loopback
Ollama provider.
[Promptfoo offline settings](https://www.promptfoo.dev/docs/faq/#how-can-i-use-promptfoo-in-a-completely-offline-environment)

Start each team with the recorded `A17` failure. Try a second command if
both teams can run the pack and identify the reversed comparison within
15 minutes with the tools installed, and at least one supplies a case from
its own assistant to keep for the next model upgrade.
