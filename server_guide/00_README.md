# PROJECTKIDCREATIONS — Server Guide (Source)

This directory is the **canonical source** for the PROJECTKIDCREATIONS Discord server guide.

## Contents

| File | Where it lives in Discord | Purpose |
|---|---|---|
| `01_welcome_embeds.md` | Pinned embeds in `#welcome` | 7-embed branded landing series |
| `02_brand_story.md` | `#server-guide` forum, thread 1 | Brand origin + thesis |
| `03_channel_map.md` | `#server-guide` forum, thread 2 | Every channel explained |
| `04_role_tiers.md` | `#server-guide` forum, thread 3 | Role hierarchy + how to earn each |
| `05_build_pipeline.md` | `#server-guide` forum, thread 4 | Build workflow + verification |
| `06_drop_pipeline.md` | `#server-guide` forum, thread 5 | Drop calendar + tiered access |
| `07_mod_reporting.md` | `#server-guide` forum, thread 6 | Mod contact + reporting + appeals |
| `08_faq.md` | `#server-guide` forum, thread 7 | Frequently asked questions |
| `09_glossary.md` | `#server-guide` forum, thread 8 | PKC + gel-blaster scene terms |
| `10_history.md` | `#server-guide` forum, thread 9 | Origin + milestones + founder note |
| `11_roadmap.md` | `#server-guide` forum, thread 10 | Vision-level direction |
| `12_reader_tracks.md` | `#server-guide` forum, thread 11 | Segmented paths for different reader types |

## Conventions

- **Voice**: Documentary / brand-book. Less casual, more authoritative.
- **Headers**: UPPERCASE (Archivo Black brand cue).
- **Body**: Mixed case for readability.
- **Versioning**: Each file has a `Version` line at the bottom. Bump on edit.
- **Colors used in embeds**: hi-vis orange `#FF5F1F`, alarm-red `#FF1F1F`, neon-green `#39FF14`.

## Publishing

Run `publish_guide.py` from the project root. It reads these files, posts each to
the right place in Discord, and pins where appropriate. Idempotent — safe to re-run
(updates existing posts by edit when possible).

```bash
cd ~/Desktop/Claude\ Projects/Top\ Shooter
source .venv/bin/activate
python publish_guide.py
```

## Editing

Edit the .md files directly. Re-run `publish_guide.py` to push changes.
For embed series in `#welcome`, the script edits existing pinned messages
(matches on the magic marker `<!-- pkc-embed-id: NN -->` in the description).
