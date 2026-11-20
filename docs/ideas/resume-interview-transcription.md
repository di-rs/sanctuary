# Resume a local transcription batch one interview at a time

An oral history editor returns to a stopped overnight batch. Two recorders
both produced a file named `001.wav`, and a reviewer has already corrected a
name in one transcript. Sanctuary could give the editor a local queue that
shows which recording produced each draft and which interviews still need
transcription.

Columbia Oral History uses Descript and MacWhisper for transcription and has
staff check transcripts. Buzz, a desktop transcription app, can reuse a
matching transcript beside a recording. Its skip plugin can also look up
a completed transcription by filename. If a team replaces a recording or
switches models, its editor needs to know which audio and model produced
the draft.
[Columbia Oral History FAQ](https://www.incite.columbia.edu/coh/about/faq)
and [Buzz's skip plugin](https://chidiwilliams.github.io/buzz/docs/usage/plugins#skip-already-transcribed)

## What counts as a finished draft

Shish runs local commands with the editor's permissions. This command wrote a
JSON draft to stdout with network access disabled on macOS. It requires
`shish` and `whisper-cli` on `PATH` and local copies of the model and WAV at
the paths shown.
[Shish command execution](../../packages/shish/README.md#run-commands)
and [the tiny English model](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-tiny.en-q5_1.bin)

```sh
shish -c 'whisper-cli -m ggml-tiny.en-q5_1.bin -l en -oj -of - -f card-a/001.wav'
```

In a local check with whisper.cpp 1.9.5, a batch containing one readable
WAV and one unreadable WAV returned exit code 11 after writing the first
draft. A single recording with an unrecognized language setting returned
zero and produced no JSON. The proposed queue would process a read-only copy
of one recording at a time. It would mark a draft ready for review when the
process exits successfully and the JSON contains a list of segments with
text and time offsets.
[whisper.cpp 1.9.5 CLI](https://github.com/ggml-org/whisper.cpp/blob/v1.9.5/examples/cli/cli.cpp)

To reuse a draft, the queue would match the recording's project-relative path,
SHA-256 hashes of the audio, model and transcriber, and the decoding settings.
It would save these and the draft in one SQLite transaction on the project
disk. An unfinished recording would start from the beginning. Each review
copy would have its own path, such as `review/card-a/001.txt`. If that file
already exists, the editor could open it or choose a new name for the export.
[Sanctuary's recovery plan](../../packages/shish/docs/durability.md#what-recovery-means)

## A restart on the same workstation

A local test worker transcribed two excerpts of the same speech through
Shish. Both files were named `001.wav`, under `card-a` and `card-b`. The
worker used one SQLite transaction per recording.
[Sample recording from whisper.cpp](https://github.com/ggml-org/whisper.cpp/blob/v1.9.5/samples/jfk.wav)

| Trial | Result on reopening |
| --- | --- |
| Kill the worker after it inserts the second draft, before it commits | Transcribed Card B and recovered Card A's draft byte for byte. |
| Open the completed batch again | Reused both drafts. |
| Replace Card A's audio, keeping its filename, size and modification time | Transcribed Card A again and kept its earlier draft. Reused Card B's draft. |
| Change the maximum segment length to 20 characters | Transcribed both recordings with the new setting. |

## Try it against the team's current workflow

Invite two oral history teams that use Buzz locally to compare its skip
plugin with the proposed queue. Give each team the same six interviews and
model on its workstation, with fresh project copies for each run. Reverse
the order between teams. Stop during the fifth interview and have an editor
correct a name in the first review copy. Time from reopening the project to
six correctly matched drafts, including model loading. Package the queue if
both teams reach that point sooner with it, run the transcriber only for the
two outstanding interviews, and keep the editor's correction.
