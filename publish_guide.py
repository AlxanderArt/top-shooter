"""
Publish the server guide to Discord.

Reads markdown files from server_guide/ and posts to PROJECTKIDCREATIONS:
- 01_welcome_embeds.md -> pinned embed series in #welcome
- 02_*.md through 12_*.md -> forum threads in #server-guide

Idempotent:
- Welcome embeds are matched by `<!-- pkc-embed-id: NN -->` marker and edited in place.
- Forum threads are matched by thread title; existing threads are skipped (use --rewrite to force).

Usage:
    python publish_guide.py            # publish (skip existing forum threads)
    python publish_guide.py --rewrite  # delete existing forum threads and re-create
"""

import os
import re
import sys
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import argparse
import asyncio
import logging

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).parent
GUIDE_DIR = ROOT / "server_guide"
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("DEV_GUILD_ID") or 0)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("publish")

BRAND_FOOTER = "TOP SHOOTER · ENGINEERED REBELLION"
ORANGE = 0xFF5F1F
RED = 0xFF1F1F
GREEN = 0x39FF14
SLATE = 0x3F4448

COLOR_NAME_TO_HEX = {
    "#FF5F1F": ORANGE, "#FF1F1F": RED, "#39FF14": GREEN, "#3F4448": SLATE,
}


# ---------------------------------------------------------------------------
# Markdown parsers
# ---------------------------------------------------------------------------
def parse_welcome_embeds(md_text: str) -> list[dict]:
    """Parse 01_welcome_embeds.md into a list of {title, color, description, marker, footer} dicts."""
    embeds = []
    # Split on "## Embed NN" headers
    sections = re.split(r"\n## Embed (\d+) [—-]", md_text)
    # sections = ["preamble", "01", " Title splash\n\n**Color:**...", "02", "...", ...]
    for i in range(1, len(sections), 2):
        num = sections[i].strip()
        body = sections[i + 1]
        # Extract fields
        color_m = re.search(r"\*\*Color:\*\*\s*`(#[0-9A-Fa-f]{6})`", body)
        marker_m = re.search(r"\*\*Marker:\*\*\s*`(<!-- pkc-embed-id:\s*\d+\s*-->)`", body)
        title_m = re.search(r"\*\*Title:\*\*\s*`(.+?)`", body)
        footer_m = re.search(r"\*\*Footer:\*\*\s*`(.+?)`", body)
        desc_m = re.search(r"\*\*Description:\*\*\n((?:>.*\n?|\n)*?)(?=\n\*\*Footer:|\n---)", body, re.DOTALL)
        if not (color_m and marker_m and title_m and desc_m):
            log.warning("Embed %s: missing fields, skipping", num)
            continue
        # Strip blockquote ">" prefixes from description
        desc_raw = desc_m.group(1)
        desc_lines = []
        for line in desc_raw.split("\n"):
            line = line.rstrip()
            if line.startswith("> "):
                desc_lines.append(line[2:])
            elif line.strip() == ">":
                desc_lines.append("")
            elif line.startswith(">"):
                desc_lines.append(line[1:])
            else:
                desc_lines.append(line)
        description = "\n".join(desc_lines).strip()
        # Append marker as zero-width-ish HTML comment-style note. Discord supports markdown comments only loosely;
        # we embed marker in the footer.text as a hidden suffix that's part of the footer but unobtrusive.
        embeds.append({
            "num": int(num),
            "title": title_m.group(1).strip(),
            "color": COLOR_NAME_TO_HEX.get(color_m.group(1).upper(), ORANGE),
            "description": description,
            "footer": footer_m.group(1).strip() if footer_m else BRAND_FOOTER,
            "marker": marker_m.group(1).strip(),
        })
    embeds.sort(key=lambda e: e["num"])
    return embeds


def parse_thread_file(md_text: str, file_path: Path) -> dict:
    """Parse a forum-thread markdown file. Returns {title, tags, color, body}."""
    title_m = re.search(r"\*\*Thread title:\*\*\s*`(.+?)`", md_text)
    tags_m = re.search(r"\*\*Tags:\*\*\s*([^\n]+)", md_text)
    color_m = re.search(r"\*\*Color:?(?: \(OP embed\))?:\*\*\s*`(#[0-9A-Fa-f]{6})`", md_text)
    # Strip everything up to and including the first standalone "---" line after the metadata block
    body_split = re.split(r"\n---\n", md_text, maxsplit=1)
    body = body_split[1].strip() if len(body_split) > 1 else md_text
    # Discord allows max 100-char thread titles
    title = (title_m.group(1).strip() if title_m else file_path.stem)[:100]
    tags = [t.strip().strip("`") for t in tags_m.group(1).split(",")] if tags_m else []
    color = COLOR_NAME_TO_HEX.get(color_m.group(1).upper(), ORANGE) if color_m else ORANGE
    return {"title": title, "tags": tags, "color": color, "body": body}


def split_for_discord(text: str, max_len: int = 1900) -> list[str]:
    """Split text into chunks of <= max_len chars, breaking on paragraph boundaries."""
    if len(text) <= max_len:
        return [text]
    chunks, current = [], ""
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        if len(para) > max_len:
            # Hard-split very long paragraph on lines
            for line in para.split("\n"):
                if len(current) + len(line) + 1 > max_len:
                    chunks.append(current.rstrip())
                    current = line + "\n"
                else:
                    current += line + "\n"
            continue
        if len(current) + len(para) + 2 > max_len:
            chunks.append(current.rstrip())
            current = para + "\n\n"
        else:
            current += para + "\n\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


# ---------------------------------------------------------------------------
# Publishers
# ---------------------------------------------------------------------------
async def ensure_server_guide_forum(guild: discord.Guild) -> discord.ForumChannel:
    forum = discord.utils.get(guild.channels, name="server-guide")
    if forum:
        log.info("· #server-guide forum exists")
        return forum
    info_cat = discord.utils.get(guild.categories, name="📋 INFO")
    if not info_cat:
        raise RuntimeError("📋 INFO category not found — run setup_server.py first")
    owner_role = discord.utils.get(guild.roles, name="Owner")
    mod_role = discord.utils.get(guild.roles, name="Mod")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True, read_message_history=True,
            send_messages_in_threads=True,
            create_public_threads=False, create_private_threads=False,
            add_reactions=True, use_application_commands=True,
        ),
    }
    if owner_role:
        overwrites[owner_role] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True,
            send_messages_in_threads=True,
            create_public_threads=True, manage_threads=True, manage_messages=True,
            add_reactions=True, embed_links=True, attach_files=True,
        )
    if mod_role:
        overwrites[mod_role] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True,
            send_messages_in_threads=True,
            create_public_threads=True, manage_threads=True, manage_messages=True,
            add_reactions=True, embed_links=True, attach_files=True,
        )
    forum = await guild.create_forum(
        name="server-guide",
        category=info_cat,
        topic="THE CANONICAL SERVER MANUAL. ONE THREAD PER TOPIC.",
        overwrites=overwrites,
        reason="publish_guide: server guide forum",
    )
    log.info("+ #server-guide forum created")
    return forum


async def publish_welcome_embeds(welcome_ch: discord.TextChannel, embeds_data: list[dict]):
    """Post or update + pin each welcome embed by marker."""
    existing = []
    async for msg in welcome_ch.history(limit=50):
        if msg.author == welcome_ch.guild.me and msg.embeds:
            existing.append(msg)

    # Match by marker text in embed footer
    def find_existing(marker: str) -> discord.Message | None:
        for m in existing:
            for emb in m.embeds:
                if emb.footer and marker in (emb.footer.text or ""):
                    return m
        return None

    for data in embeds_data:
        emb = discord.Embed(
            title=data["title"],
            description=data["description"],
            color=data["color"],
        )
        # Hide marker as a trailing space-separated suffix in footer
        emb.set_footer(text=f"{data['footer']} · {data['marker']}")
        existing_msg = find_existing(data["marker"])
        if existing_msg:
            await existing_msg.edit(embed=emb)
            log.info("  · embed %02d updated", data["num"])
            if not existing_msg.pinned:
                try:
                    await existing_msg.pin()
                except discord.HTTPException as e:
                    log.warning("    could not pin: %s", e)
        else:
            msg = await welcome_ch.send(embed=emb)
            try:
                await msg.pin()
            except discord.HTTPException as e:
                log.warning("  ! could not pin embed %02d: %s", data["num"], e)
            log.info("  + embed %02d posted + pinned", data["num"])


async def publish_forum_thread(forum: discord.ForumChannel, thread_spec: dict, rewrite: bool = False):
    """Create (or skip) a forum thread, posting the body in chunks."""
    existing = None
    for t in forum.threads:
        if t.name == thread_spec["title"]:
            existing = t
            break
    if existing and not rewrite:
        log.info("  · thread exists, skipping: %s", thread_spec["title"])
        return
    if existing and rewrite:
        await existing.delete(reason="publish_guide --rewrite")
        log.info("  · deleted existing thread: %s", thread_spec["title"])

    chunks = split_for_discord(thread_spec["body"], max_len=1900)
    first = chunks[0]
    thread_with_msg = await forum.create_thread(
        name=thread_spec["title"],
        content=first,
        reason="publish_guide",
    )
    thread = thread_with_msg.thread
    log.info("  + thread created: %s (%d chunks)", thread_spec["title"], len(chunks))
    for chunk in chunks[1:]:
        await thread.send(chunk)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(args):
    if not (TOKEN and GUILD_ID):
        sys.exit("Missing DISCORD_TOKEN or DEV_GUILD_ID in .env")

    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            await run(client, args)
        except Exception:
            log.exception("publish failed")
        finally:
            await client.close()

    await client.start(TOKEN)


async def run(client: discord.Client, args):
    guild = client.get_guild(GUILD_ID)
    if not guild:
        log.error("Guild %s not found", GUILD_ID)
        return

    log.info("== publishing server guide to %s ==", guild.name)

    # Step 1 — Welcome embeds
    log.info("[1/2] Welcome embeds in #welcome...")
    welcome_md = (GUIDE_DIR / "01_welcome_embeds.md").read_text()
    embeds = parse_welcome_embeds(welcome_md)
    log.info("  · parsed %d embeds", len(embeds))
    welcome_ch = discord.utils.get(guild.text_channels, name="welcome")
    if not welcome_ch:
        log.error("  ! #welcome channel not found")
    else:
        await publish_welcome_embeds(welcome_ch, embeds)

    # Step 2 — Server guide forum threads
    log.info("[2/2] Forum threads in #server-guide...")
    forum = await ensure_server_guide_forum(guild)
    thread_files = sorted(
        f for f in GUIDE_DIR.glob("[01]*.md")
        if not f.name.startswith("01_") and not f.name.startswith("00_")
    )
    for tf in thread_files:
        md = tf.read_text()
        spec = parse_thread_file(md, tf)
        if not spec["body"].strip():
            log.warning("  ! %s has no body, skipping", tf.name)
            continue
        await publish_forum_thread(forum, spec, rewrite=args.rewrite)

    log.info("== publish complete ==")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rewrite", action="store_true", help="delete existing forum threads and re-create")
    args = p.parse_args()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        log.info("Cancelled.")
