# Keep both edits when a coding assistant changes an open file

A developer lowers a retry limit in Kara, Sanctuary's terminal editor.
Before they save, their coding assistant changes the output format in the
same file. At the next save, a proposed **Review disk changes** action
would show a copy with both edits. If the two writers chose different
values for one setting, the developer would decide which to keep.

With Aider's `--watch-files` option, a developer can request an edit by
saving an `AI!` comment and keep working while Aider updates the file.
A Helix user described redoing unsaved work from memory after an external
change and asked for a merge using the version they originally opened.
[Aider's editor workflow](https://aider.chat/docs/usage/watch.html)
and [the Helix user's account](https://github.com/helix-editor/helix/discussions/8468)

## Which version preserves both edits?

In a macOS terminal trial with Kara 0.2.0, a second process changed
`format=text` to `format=json` while an unsaved retry edit was on screen.
Ctrl-S saved the retry edit and put `format=text` back on disk. If you
notice the external edit first, press Esc, type `:w buffer` and press
Enter, using a fresh filename for `buffer`. Kara switches to that copy.
You can then compare it with the other process's version at the original path.
[Kara's save commands](../../packages/kara/README.md#controls)

If you also have the version you started editing, Git can combine the two
copies. Try this example in an empty directory with Git and `sed`. The
last commit specified two retries. The developer opened a file with an
uncommitted increase to three and deliberately changed it back to two.

```sh
printf '%s\n' 'retries=2' 'timeout=30' 'format=text' > committed
sed 's/retries=2/retries=3/' committed > opened
sed 's/retries=3/retries=2/' opened > buffer
sed 's/format=text/format=json/' opened > disk

git merge-file -p buffer opened disk
git merge-file -p buffer committed disk
```

Both merges print a file and exit zero. With `opened` as the common
ancestor, the result has `retries=2` and `format=json`. With `committed`,
Git sees the buffer as identical to its ancestor and takes the disk
version, including `retries=3`.
[Git's three-way file merge](https://git-scm.com/docs/git-merge-file)

## Review the save in Kara

Kara could keep the contents it opened or last saved in memory. When a
developer saves an edited file, Kara would compare that original, the
buffer and the current file on disk. If both versions changed and they
disagree, Kara would pause the save and show each edit.

The editor could merge all three versions in memory with libgit2. In a
local trial, changing the retry count to four on disk produced one conflict.
Git's command exited 1. The libgit2 function returned zero with
`automergeable=false`. For that result, Kara would show the opened value
(3), the developer's value (2) and the disk value (4).
[libgit2's in-memory merge](https://libgit2.org/docs/reference/v1.9.7/merge/git_merge_file.html)
and [merge result](https://libgit2.org/docs/reference/v1.9.7/merge/git_merge_file_result.html)

Before exporting the reviewed result to a new filename, Kara would check
the buffer revision and reread the disk file. A change would prompt
**Review again**. If the file were missing or unreadable, the developer
could still save the buffer separately. Once the assistant finishes, the
developer could compare the reviewed copy with the working file and apply it.

## Compare with Vorto before building

In Vorto's `config.toml`, setting `autoreload = "merge"` under `[editor]`
merges disk changes as they arrive. In the same macOS trial, Vorto 0.15.4
saved both independent edits byte for byte, including in a file with mixed
line endings and no final newline. When both writers changed the retry
count, it marked the conflict in the buffer.
[Vorto's auto-reload settings](https://github.com/vorto-editor/vorto/blob/v0.15.4/README.md#auto-reload)

Try Kara with four developers who want to finish typing before reviewing
an assistant's edits. Have each bring a file where that timing mattered.
Compare the proposed action with Vorto's merge mode or the developer's
usual merge tool. Give both tools equivalent edits, specify the desired
settings and alternate which tool each person tries first.

Try independent edits on an uncommitted starting file, two edits to the
same setting, and a second disk edit while the first is under review.
Time each task from opening the file to verifying the final bytes,
including preparing copies and applying the result. Continue if all four
developers preserve the requested edits and line endings in every case
and at least three save a minute on the file they brought.
