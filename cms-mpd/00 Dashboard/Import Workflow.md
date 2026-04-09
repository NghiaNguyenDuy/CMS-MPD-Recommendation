---
title: Import Workflow
type: guide
tags:
  - cms-mpd
  - workflow
---

# Import Workflow

Use this flow when you bring new references, articles, or markdown exports into the vault.

## Capture Flow

1. Save raw markdown files into `01 Inbox/Articles`, `01 Inbox/References`, or `01 Inbox/Web Imports`.
2. Save supporting files into `materials/PDFs`, `materials/Images`, or `materials/Attachments`.
3. Create a reviewed note in `02 Source Notes` using [[Article Note Template]] or [[Reference Note Template]].
4. Turn repeated insights into a concept note in `03 Topic Notes` using [[Topic Note Template]].
5. Keep active questions or study sessions in `04 Study Notes`.
6. Move old material to `99 Archive` when it is no longer useful.

## Naming Pattern

- Raw imports: `YYYY-MM-DD Source Title.md`
- Source notes: `Source - Short Title.md`
- Topic notes: `Topic - Concept Name.md`
- Study notes: `Study - Session Name.md`

> [!tip]
> Leave raw source files mostly unchanged in `01 Inbox`. Put your interpretation, summaries, and connections in `02 Source Notes`, `03 Topic Notes`, and `04 Study Notes`.

## Minimum Metadata For Reviewed Sources

- Source title
- URL or local file path
- Publication or effective date
- Why it matters
- Linked topic notes

## Processing Loop

- `01 Inbox` -> raw source material
- `02 Source Notes` -> reviewed source summary
- `03 Topic Notes` -> distilled knowledge
- `05 Outputs` -> reusable study material
