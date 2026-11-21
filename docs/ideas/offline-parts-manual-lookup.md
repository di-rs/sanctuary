# Find the drawing for a part number offline

A printer repair ticket calls for feed roller `PR-274`. Before placing the
order, the technician wants to show the parts desk where that number appears
in the supplier's PDF. A proposed local Sanctuary CLI would take the manual
and the number from the ticket, then list the pages to inspect in the original.
The desk could reopen the cited drawing offline.

HP PartSurfer lets technicians identify parts visually when a diagram is
available. Quanos lets field crews download machine-specific catalogs and
use their drawings offline. A repair desk that receives only supplier PDFs
could use the CLI with the manuals it already keeps on its laptops.
[HP PartSurfer user guide](https://partsurfer.hp.com/PartSurfer/UserGuide)
and [Quanos IQ for Parts](https://quanos.com/en/products/iq-for-parts/)

## Why the adapter looks like a match

In a two-page synthetic manual, page 1 lists the adapter `PR-274-A` as
selectable text. Page 2 has a selectable heading and a drawing with the
roller's number printed inside the image. A Paperless-ngx user reported
finding the body text of an invoice in search while words in its header
and footer images were missing. [Paperless-ngx mixed-page report](https://github.com/paperless-ngx/paperless-ngx/discussions/1637)

| Copy searched with pdfgrep | Pages containing the string `PR-274` | Pages containing the whole code `PR-274` |
| --- | --- | --- |
| Original PDF | 1 | None |
| OCRmyPDF with `--mode skip` | 1 | None |
| OCRmyPDF with `--mode redo` | 1 and 2 | 2 |

Matching the whole code, including its hyphens, excluded the adapter.
Skip mode saw page 2's heading and skipped the page. Redo mode masked the
selectable text and ran optical character recognition (OCR) on the drawing.
It recovered the roller number and read part of the drawing as a stray
`L` beside it. Opening page 2 shows which component the label points to.
[OCRmyPDF processing modes](https://ocrmypdf.readthedocs.io/en/stable/advanced.html#when-ocr-is-skipped)
and [pdfgrep page numbers and search options](https://pdfgrep.org/manpages/manpage-2.1.2.html)

## What goes in the repair ticket

Sanctuary's `grepr` searches lines of UTF-8 text. A separate CLI could
use OCRmyPDF to make a local searchable copy and pdfgrep to find the pages.
The technician could inspect each match in the original and attach the
confirmed reference to the ticket as **PR-274 · feeder.pdf · PDF page 2**.
The ticket would store the original PDF's SHA-256 alongside that reference.
When a colleague opens it, the ticket app would check the fingerprint and
ask for the cited edition if the supplier had replaced the file. An unreadable
page or a search with no exact hit would prompt a manual lookup.
[Sanctuary's text search](../../buildins/grepr/README.md)

## Try it at a parts desk

Ask one desk for eight closed tickets and the corresponding manual editions.
Include an image label, two codes that differ by a suffix, an absent code
and a supplier revision with the same filename. Have two technicians each
work all eight tickets. Alternate which technician uses the CLI on each
ticket. Give the other the same OCR settings and exact-code search as a
saved script, along with the desk's PDF viewer and checksum tool.

Time each lookup through a colleague checking the drawing or recording a
manual lookup. Divide each method's preparation time for a manual edition
among the tickets that use it. Try a second desk if the CLI gives the correct
drawing and edition for every known part, sends the absent code to manual
review and saves at least one minute per ticket at the median. If the saved
script performs as well, give it to the desk.

<details>
<summary>Reproduce the two-page comparison</summary>

Start in an empty directory with uv, Docker and pdfgrep 2.1.2. The fixture
generator uses ReportLab and Pillow. Download the Python packages and
OCRmyPDF image before taking the tools offline.

```sh
uv run --no-project --with reportlab==4.5.1 --with pillow==12.3.0 python - <<'PY'
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

manual = canvas.Canvas("feeder.pdf", pagesize=(360, 240), invariant=1)
manual.setFont("Helvetica-Bold", 18)
manual.drawString(24, 198, "Desk printer / Adapter kit")
manual.setFont("Helvetica", 14)
manual.drawString(24, 150, "PR-274-A   Feed roller adapter")
manual.showPage()
manual.setFont("Helvetica-Bold", 18)
manual.drawString(24, 198, "Desk printer / Feed roller")
diagram = Image.new("RGB", (1200, 500), "white")
draw = ImageDraw.Draw(diagram)
draw.rounded_rectangle((100, 80, 490, 240), 60, outline="black", width=6)
draw.line([(470, 220), (550, 290), (610, 290)], fill="black", width=5)
draw.text((620, 250), "PR-274", font=ImageFont.load_default(size=70), fill="black")
manual.drawImage(ImageReader(diagram), 24, 42, width=312, height=130)
manual.save()
PY
```

```sh
docker pull jbarlow83/ocrmypdf-alpine:v17.14.2
for mode in skip redo
do
  docker run --rm -i --pull never --network none jbarlow83/ocrmypdf-alpine:v17.14.2 \
    --mode "$mode" --output-type pdf --optimize 0 --jobs 1 - - \
    < feeder.pdf > "$mode.pdf"
done
```

The first search accepts the code anywhere in a longer string. The second
treats letters, digits and hyphens as part of the code. Each hit includes
the filename and PDF page number.

```sh
pdfgrep -HnF PR-274 feeder.pdf skip.pdf redo.pdf
LC_ALL=C pdfgrep -Hn '(^|[^[:alnum:]-])PR-274([^[:alnum:]-]|$)' \
  feeder.pdf skip.pdf redo.pdf
```

</details>
