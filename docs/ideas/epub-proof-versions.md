# Check the exact EPUB revision an editor plans to send

A production editor fixes a broken link in a book's table of contents and
uploads the correction under the same filename. If the first check is still
queued, it can read the correction and mark the broken proof as passed.
For a publisher that stages books in a versioned Amazon S3 bucket,
Sanctuary could put a verdict beside each upload in the production tracker.
An editor could select a passing revision and download that copy for delivery.

Apple Books requires EPUB submissions to pass the latest EPUBCheck, the
conformance checker for this ebook format. Storytel runs it at intake and
asks publishers to use the book's ISBN as its filename.
[Apple Books submission requirements](https://itunespartner.apple.com/books/support/9-prepare-book)
and [Storytel file requirements](https://publishersupport.storytel.com/hc/en-us/articles/16693703061020-Ebook-file-formats-and-requirements)

FlightDeck gives editors validation and retailer-specific reports for each
uploaded EPUB. A desk that checks unreleased proofs in-house can download
a specific S3 version and run EPUBCheck locally. A private connector would
save the editor the work of matching each report to the file it checked.
[FlightDeck reports](https://ebookflightdeck.com/reports)
and [running EPUBCheck locally](https://www.w3.org/publishing/epubcheck/docs/running/)

## What a delayed check can report

In a local trial, Moto, an S3 emulator, stored two synthetic EPUBs under
one filename. The trial used the ZIP extractor from Boxie, Sanctuary's
sandbox runtime, to unpack each book from its outer ZIP. EPUBCheck 5.4.0
read the intact EPUB in a Linux container on Docker Desktop with networking
disabled.

| Requested proof | How the trial fetched it after the correction | EPUBCheck result |
| --- | --- | --- |
| Original | Filename alone | Passed the corrected book, exit 0 |
| Original | Original upload's version ID | Found the broken chapter link (`RSC-007`), exit 1 |
| Correction | Corrected upload's version ID | Passed, exit 0 |

The test delivered the correction's notification first, then the original
twice. Reading by version produced two verdicts from two checker launches.
Uploading the corrected bytes once more preserved the ETag and produced
a new version ID. A tracker keyed by ETag would merge those two uploads.

With versioning suspended, the literal version ID `null` returned different
books before and after an overwrite. If the ID is missing or null, or the
version has been deleted, flag the notification as **Source unavailable**.
A fresh upload to a version-enabled bucket can receive its own verdict.
[S3 writes with versioning suspended](https://docs.aws.amazon.com/AmazonS3/latest/userguide/AddingObjectstoVersionSuspendedBuckets.html)

## From a storage notification to a verdict

A service on the publisher's network would read upload notifications from
an Amazon SQS queue restricted to the publisher's bucket. It would decode
the object key and call `GetObject` with the event's version ID, using
`s3:GetObjectVersion` permission for the intake prefix. The service would
hold the storage credentials and Boxie consumer secret. The sandbox would
receive the book as a read-only file. Start with EPUBs up to 64 MiB,
Boxie's ceiling for one ZIP member.
[S3 event fields](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html),
[version-specific reads](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)
and [Boxie artifact limits](../../packages/boxie/src/boxie/persistence/artifacts.py)

Use one tracker row per bucket, key and version. Until Boxie confirms job
submission, save the original ZIP containing `book.epub`, its artifact ID
and the submission key so a retry can reuse all three. The operator would
grant the service a Boxie profile with a pinned image containing Java and
EPUBCheck. The trial used this command.

```sh
/opt/java/openjdk/bin/java -Xmx192m -jar /opt/epubcheck/epubcheck.jar \
  --quiet --json - /opt/artifact/book.epub
```

Each row would show the checker release. A complete JSON report and exit
zero would earn **EPUBCheck passed**. The broken proof would show the link
and error code. A truncated report or an unknown job outcome would leave
the row awaiting review. The tracker would check the editor's access to
the title before serving the report or the book.
[EPUBCheck report options](https://www.w3.org/publishing/epubcheck/docs/cli/)
and [Boxie job submission and results](../../packages/boxie/docs/consumer-api.md#submit-a-job-and-retrieve-its-result)

## Try it at a production desk

Give two production editors the same six pairs of small proofs. Each
editor uses the connector for three pairs and the desk's current process
for three. Swap assignments between editors and use the same checker
release. Make the newer revision fail in half the pairs. Delay and repeat
an upload notification, and delete one passing version before its check.
Count hands-on minutes from opening the request until the editor retrieves
the passing copy or identifies the unavailable proof. Check each verdict
against the answer key and compare any downloaded copy byte for byte.

Run the pilot with S3 notifications and a native Linux/gVisor Boxie host.
Use last month's correction volume to estimate the editor time saved. Try
a month of live intake if every verdict and download matches its upload
and the projected savings cover setup and a month of operator time.
