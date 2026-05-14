"""
PROJECTKIDCREATIONS — server build script.

Builds PROJECTKIDCREATIONS (Discord guild) from a blank slate to the full
layout: 7 categories, ~22 channels, 11 hierarchy roles, 14 tag/ping roles,
Community feature, Stage channel, Forum channel, Announcement channel,
verification level High, AutoMod (spam + slurs + mention-spam), and 5-prompt
onboarding flow.

Idempotent — safe to re-run. Existing roles/channels are matched by name and
reused; new ones are created.

Usage:
    cd ~/Desktop/Claude\\ Projects/Top\\ Shooter
    source .venv/bin/activate
    python setup_server.py
"""

import os
import sys
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import asyncio
import logging
from datetime import timedelta

import discord
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("DEV_GUILD_ID") or 0)
OWNER_ID = int(os.getenv("OWNER_ID") or 0)

if not (TOKEN and GUILD_ID and OWNER_ID):
    sys.exit("Missing DISCORD_TOKEN, DEV_GUILD_ID, or OWNER_ID in .env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("setup")

# ---------------------------------------------------------------------------
# Brand palette
# ---------------------------------------------------------------------------
ORANGE = discord.Color(0xFF5F1F)
ORANGE_DARK = discord.Color(0xCC4400)
ORANGE_LIGHT = discord.Color(0xFF8C42)
RED = discord.Color(0xFF1F1F)
SLATE = discord.Color(0x3F4448)
WHITE = discord.Color(0xE8E8E8)
GOLD = discord.Color(0xFFD700)
NEON_GREEN = discord.Color(0x39FF14)
PURPLE = discord.Color(0x9966FF)
TACTICAL_BLACK = discord.Color(0x0A0A0A)
TAC_BLUE = discord.Color(0x1E90FF)
GREY = discord.Color(0x666666)
NONE = discord.Color.default()

# ---------------------------------------------------------------------------
# Roles (hierarchy: index 0 = highest, last = lowest above @everyone)
# ---------------------------------------------------------------------------
HIERARCHY_ROLES = [
    {"name": "Owner", "color": ORANGE, "hoist": True, "mentionable": False, "perms": "admin"},
    {"name": "Founder", "color": TACTICAL_BLACK, "hoist": True, "mentionable": True, "perms": "admin"},
    {"name": "Mod", "color": RED, "hoist": True, "mentionable": True, "perms": "mod"},
    {"name": "Designer", "color": WHITE, "hoist": True, "mentionable": True, "perms": "designer"},
    # Top Shooter (the bot's own role) is auto-created by OAuth. We don't create it;
    # we just position it below Designer at runtime.
    {"name": "VIP", "color": NEON_GREEN, "hoist": True, "mentionable": False, "perms": "member"},
    {"name": "Verified Builder", "color": ORANGE_LIGHT, "hoist": True, "mentionable": False, "perms": "member"},
    {"name": "Beta Tester", "color": PURPLE, "hoist": True, "mentionable": False, "perms": "member"},
    {"name": "New Shooter", "color": TAC_BLUE, "hoist": False, "mentionable": False, "perms": "member"},
    {"name": "Recruit", "color": NONE, "hoist": False, "mentionable": False, "perms": "recruit"},
]

# Tag roles — sit below the hierarchy roles, ordered for sidebar grouping.
TAG_ROLES = [
    # Age gate (onboarding required)
    {"name": "18+", "color": ORANGE, "hoist": False, "mentionable": False},
    {"name": "14-17", "color": GREY, "hoist": False, "mentionable": False},
    # Identity (onboarding Q1)
    {"name": "Partner", "color": GOLD, "hoist": False, "mentionable": True},
    # Build experience (onboarding Q4)
    {"name": "Builder · Newbie", "color": NONE, "hoist": False, "mentionable": False},
    {"name": "Builder · Intermediate", "color": NONE, "hoist": False, "mentionable": False},
    {"name": "Builder · Expert", "color": NONE, "hoist": False, "mentionable": False},
    # Ping roles (onboarding Q3 + self-serve later)
    {"name": "Pings · Drops", "color": RED, "hoist": False, "mentionable": True},
    {"name": "Pings · Events", "color": ORANGE, "hoist": False, "mentionable": True},
    {"name": "Pings · Beta", "color": PURPLE, "hoist": False, "mentionable": True},
    {"name": "Pings · Silent", "color": GREY, "hoist": False, "mentionable": False},
    {"name": "Pings · Build Streams", "color": ORANGE_LIGHT, "hoist": False, "mentionable": True},
    {"name": "Pings · Mod Drops", "color": ORANGE_LIGHT, "hoist": False, "mentionable": True},
    {"name": "Pings · Range Meetups", "color": SLATE, "hoist": False, "mentionable": True},
    {"name": "Pings · Anniversary", "color": GOLD, "hoist": False, "mentionable": True},
    # Referral source (onboarding Q5) — analytics tags, no perms
    {"name": "Found · Friend", "color": NONE, "hoist": False, "mentionable": False},
    {"name": "Found · Social", "color": NONE, "hoist": False, "mentionable": False},
    {"name": "Found · Video", "color": NONE, "hoist": False, "mentionable": False},
    {"name": "Found · Search", "color": NONE, "hoist": False, "mentionable": False},
    {"name": "Found · Event", "color": NONE, "hoist": False, "mentionable": False},
]


def perms_for(label: str) -> discord.Permissions:
    if label == "admin":
        return discord.Permissions.all()
    if label == "mod":
        p = discord.Permissions.none()
        p.update(
            kick_members=True, ban_members=True, moderate_members=True,
            manage_messages=True, manage_threads=True, manage_nicknames=True,
            view_audit_log=True, mute_members=True, deafen_members=True,
            move_members=True, manage_events=True,
            read_messages=True, send_messages=True, embed_links=True,
            attach_files=True, add_reactions=True, use_external_emojis=True,
            read_message_history=True, connect=True, speak=True,
            request_to_speak=True, use_application_commands=True,
            send_messages_in_threads=True, create_public_threads=True,
            create_private_threads=True,
        )
        return p
    if label == "designer":
        p = discord.Permissions.none()
        p.update(
            manage_messages=True, manage_threads=True, manage_events=True,
            read_messages=True, send_messages=True, embed_links=True,
            attach_files=True, add_reactions=True, use_external_emojis=True,
            read_message_history=True, connect=True, speak=True,
            send_messages_in_threads=True, create_public_threads=True,
            use_application_commands=True,
        )
        return p
    if label == "member":
        p = discord.Permissions.none()
        p.update(
            read_messages=True, send_messages=True, embed_links=True,
            attach_files=True, add_reactions=True, use_external_emojis=True,
            read_message_history=True, connect=True, speak=True,
            stream=True, use_voice_activation=True,
            send_messages_in_threads=True, create_public_threads=True,
            use_application_commands=True,
        )
        return p
    if label == "recruit":
        # Recruits can read but not post — they post only after completing onboarding,
        # at which point they get @New Shooter from onboarding answers (or Verified Builder).
        p = discord.Permissions.none()
        p.update(
            read_messages=True, read_message_history=True,
            add_reactions=True, use_application_commands=True,
            connect=True,
        )
        return p
    return discord.Permissions.none()


# ---------------------------------------------------------------------------
# Channel topology
# ---------------------------------------------------------------------------
# visibility:
#   "public"  — visible to @everyone
#   "members" — visible only to @New Shooter+ (recruits can't see; gate via onboarding)
#   "staff"   — visible only to @Mod+
#   "founder" — visible only to @Owner+ (Founder + Owner)
# post_role: minimum role required to post (None = anyone who can see can post)
# slowmode: seconds
CATEGORIES = [
    {
        "name": "📋 INFO",
        "visibility": "public",
        "channels": [
            {"name": "welcome", "type": "text", "topic": "WELCOME TO THE RANGE. START HERE. COMPLETE ONBOARDING TO UNLOCK ACCESS.", "post_role": "Mod"},
            {"name": "rules", "type": "text", "topic": "RULES OF ENGAGEMENT. READ BEFORE POSTING.", "post_role": "Mod"},
            {"name": "announcements", "type": "text", "topic": "OFFICIAL CALLS FROM COMMAND. NO REPLIES.", "post_role": "Mod"},
            {"name": "drops", "type": "news", "topic": "GEAR DROPS. PRODUCT RELEASES. FOLLOW FOR INTEL.", "post_role": "Mod"},
        ],
    },
    {
        "name": "🎯 COMMUNITY",
        "visibility": "public-readonly",
        "channels": [
            {"name": "general", "type": "text", "topic": "THE BARRACKS. CASUAL CHATTER. UNLOCK POSTING BY COMPLETING ONBOARDING.", "slowmode": 5},
            {"name": "showcase", "type": "text", "topic": "SHOW YOUR WORK. GEAR, BUILDS, RANGE PHOTOS.", "slowmode": 10},
            {"name": "off-topic", "type": "text", "topic": "EVERYTHING ELSE. KEEP IT CIVIL."},
        ],
    },
    {
        "name": "🛠️ BUILDS-MODS",
        "visibility": "members",
        "channels": [
            {"name": "print-files", "type": "forum", "topic": "FILE DROPS. STL · 3MF · STEP. ONE BUILD PER THREAD.", "post_role": "Verified Builder"},
            {"name": "build-help", "type": "text", "topic": "STUCK ON A PRINT OR BUILD? POST HERE."},
            {"name": "mod-talk", "type": "text", "topic": "MOD DESIGN DISCUSSION. SPECS, IDEAS, REFERENCES."},
        ],
    },
    {
        "name": "🤖 BOT",
        "visibility": "members",
        "channels": [
            {"name": "bot-commands", "type": "text", "topic": "RUN BOT COMMANDS HERE. /HELP TO SEE WHAT'S LIVE.", "slowmode": 30},
            {"name": "bot-logs", "type": "text", "topic": "BOT ACTIVITY LOG. AUTOMATED.", "post_role": "Mod"},
        ],
    },
    {
        "name": "🎙️ VOICE",
        "visibility": "members",
        "channels": [
            {"name": "PKC Stage", "type": "stage", "topic": "OFFICIAL STAGE. EVENTS, AMA, RELEASES."},
            {"name": "Range 1", "type": "voice"},
            {"name": "Range 2", "type": "voice"},
            {"name": "+ NEW VOICE", "type": "voice", "topic": "Join to spawn your own temp channel."},
        ],
    },
    {
        "name": "🔒 STAFF",
        "visibility": "staff",
        "channels": [
            {"name": "mod-chat", "type": "text", "topic": "STAFF ONLY. MOD COMMS."},
            {"name": "audit-log", "type": "text", "topic": "BOT-DRIVEN AUDIT TRAIL. KICK · BAN · ROLE CHANGES.", "post_role": "Mod"},
            {"name": "planning", "type": "text", "topic": "ROADMAP, WEEKLY OPS, COORDINATION."},
            {"name": "drops-pipeline", "type": "text", "topic": "UNRELEASED PRODUCT TALK. DO NOT SCREENSHOT."},
            {"name": "partnerships", "type": "text", "topic": "AFFILIATE + PARTNER OPS."},
        ],
    },
    {
        "name": "👁️ FOUNDER",
        "visibility": "founder",
        "channels": [
            {"name": "founder-log", "type": "text", "topic": "FOUNDER NOTES. PRIVATE."},
            {"name": "ideas", "type": "text", "topic": "WHATEVER ROLLS AROUND THE HEAD. PRIVATE."},
            {"name": "scratchpad", "type": "text", "topic": "RAW DRAFTS. PRIVATE."},
        ],
    },
]

# ---------------------------------------------------------------------------
# Rules text (PKC milspec voice)
# ---------------------------------------------------------------------------
RULES_TEXT = """# RULES OF ENGAGEMENT

**By being here, you've agreed to the rules. No exceptions.**

**RULE 01 — HOLD THE LINE.**
No hate, slurs, harassment, or targeted bigotry. Zero tolerance. Instant timeout, possible ban.

**RULE 02 — NO DOXXING.**
Don't share anyone's personal info (real name, address, employer, etc.) without explicit permission. Includes your own — don't post it where you can't take it back.

**RULE 03 — STAY ON BRAND.**
Channels have topics. Read them. Off-topic chatter belongs in `#off-topic`. Tactical content stays on the range; politics and religion stay out.

**RULE 04 — KEEP IT SAFE.**
No advice that promotes unsafe use of gel-blasters or 3D-printed gear. Eye-pro always. No pointing at non-consenting humans. No real-firearm content — this is gel-blaster territory.

**RULE 05 — NO PIRACY.**
Don't share copyrighted STL/3MF files you don't have rights to redistribute. Don't post leaked PKC files. Designers deserve credit and revenue.

**RULE 06 — NO SPAM, NO ADS.**
No DM advertising, no link-shilling, no crypto/NFT promotion, no follow-for-follow. Partnerships go through staff (`#partnerships`).

**RULE 07 — NSFW STAYS OUT.**
This server is 14+. No NSFW content anywhere, even spoilered. No suggestive avatars or names. Marketing surfaces are 18+ only and gated by role.

**RULE 08 — NO ALT ACCOUNTS.**
One person, one account. Ban evasion is permanent.

**RULE 09 — MOD AUTHORITY IS FINAL.**
Mods make calls in real time. You can appeal in DMs, never publicly. Argue with a mod in-channel and you'll be the one timed out.

**RULE 10 — SUIT UP.**
React with the green check below to confirm you've read and agreed. Then complete onboarding to enter the range.

— ENGINEERED REBELLION."""

# ---------------------------------------------------------------------------
# Welcome embed (pinned in #welcome)
# ---------------------------------------------------------------------------
def build_welcome_embed():
    embed = discord.Embed(
        title="WELCOME TO THE RANGE.",
        description=(
            "You've stepped into **PROJECTKIDCREATIONS** — the home of PKC tactical gear, "
            "3D-printed mods, and the operators who run them.\n\n"
            "**FIRST STEPS:**\n"
            "`01.` Read **#rules** and accept.\n"
            "`02.` Complete onboarding (5 quick questions).\n"
            "`03.` Drop into **#general** and introduce yourself.\n\n"
            "**THE RANGE IS YOURS.**"
        ),
        color=ORANGE,
    )
    embed.set_footer(text="TOP SHOOTER · ENGINEERED REBELLION")
    return embed


# ---------------------------------------------------------------------------
# Onboarding prompts (5 funnel questions)
# ---------------------------------------------------------------------------
def build_onboarding_prompts(guild: discord.Guild):
    """Build the 5 funnel onboarding prompts. Returns list[OnboardingPrompt]."""

    def r(name: str) -> discord.Role | None:
        return discord.utils.get(guild.roles, name=name)

    def opt(title: str, *, description: str = "", role_names: list[str] | None = None, channel_names: list[str] | None = None, emoji: str | None = None):
        roles = [r(n) for n in (role_names or []) if r(n)]
        channels = [c for n in (channel_names or []) for c in guild.channels if c.name == n]
        kwargs = dict(title=title, description=description, roles=roles, channels=channels)
        if emoji:
            kwargs["emoji"] = discord.PartialEmoji(name=emoji)
        return discord.OnboardingPromptOption(**kwargs)

    prompts = []

    # Q1 — Identity (required, single)
    prompts.append(discord.OnboardingPrompt(
        type=discord.OnboardingPromptType.multiple_choice,
        title="What brings you to PKC?",
        single_select=True,
        required=True,
        in_onboarding=True,
        options=[
            opt("Browsing or collecting", description="Here for the gear and drops.", role_names=["New Shooter"], emoji="🔍"),
            opt("I print & build", description="Maker. New Shooter. Designer.", role_names=["New Shooter", "Verified Builder"], emoji="🛠️"),
            opt("Just watching the range", description="Lurker mode. Welcome.", role_names=["New Shooter"], emoji="👀"),
            opt("Affiliate / partner", description="Tagged for partnerships ops.", role_names=["New Shooter", "Partner"], emoji="🤝"),
            opt("Staff invite", description="Pending verification by command.", role_names=["New Shooter"], emoji="⭐"),
        ],
    ))

    # Q2 — Age (required, single)
    prompts.append(discord.OnboardingPrompt(
        type=discord.OnboardingPromptType.multiple_choice,
        title="Age confirmation",
        single_select=True,
        required=True,
        in_onboarding=True,
        options=[
            opt("I'm 18+", description="Unlocks drops + marketing channels.", role_names=["18+"], emoji="🔓"),
            opt("I'm 14–17", description="Full community access. No marketing-targeted content.", role_names=["14-17"], emoji="🪪"),
        ],
    ))

    # Q3 — Pings (optional, multi)
    prompts.append(discord.OnboardingPrompt(
        type=discord.OnboardingPromptType.multiple_choice,
        title="What pings do you want?",
        single_select=False,
        required=False,
        in_onboarding=True,
        options=[
            opt("Drops", description="New product releases.", role_names=["Pings · Drops"], emoji="🔴"),
            opt("Events", description="Range meetups, AMAs, live drops.", role_names=["Pings · Events"], emoji="🟠"),
            opt("Beta tester", description="Early access to unreleased gear.", role_names=["Pings · Beta"], emoji="🟡"),
            opt("Build streams", description="Live builds and walkthroughs.", role_names=["Pings · Build Streams"], emoji="🔧"),
            opt("Silent — never ping me", description="Opts out of all pings.", role_names=["Pings · Silent"], emoji="⚪"),
        ],
    ))

    # Q4 — Build experience (shown after onboarding in the role customize panel)
    prompts.append(discord.OnboardingPrompt(
        type=discord.OnboardingPromptType.multiple_choice,
        title="How deep are you on builds?",
        single_select=True,
        required=False,
        in_onboarding=False,
        options=[
            opt("Newbie — first build", description="Welcome aboard. We'll help.", role_names=["Builder · Newbie"], emoji="🌱"),
            opt("Intermediate", description="Few builds in. Comfortable with the basics.", role_names=["Builder · Intermediate"], emoji="⚙️"),
            opt("Expert / designer", description="Years deep. Designing your own mods.", role_names=["Builder · Expert"], emoji="🏆"),
        ],
    ))

    # Q5 — Referral (customize panel only)
    prompts.append(discord.OnboardingPrompt(
        type=discord.OnboardingPromptType.multiple_choice,
        title="How'd you find PKC?",
        single_select=True,
        required=False,
        in_onboarding=False,
        options=[
            opt("Friend referral", description="Word of mouth.", role_names=["Found · Friend"], emoji="👥"),
            opt("Social media", description="Instagram, X, TikTok.", role_names=["Found · Social"], emoji="📱"),
            opt("YouTube / stream", description="A build or review video.", role_names=["Found · Video"], emoji="🎥"),
            opt("Google / search", description="Found us online.", role_names=["Found · Search"], emoji="🔎"),
            opt("Range event in person", description="Met us at a meetup.", role_names=["Found · Event"], emoji="🎯"),
        ],
    ))

    return prompts


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------
async def ensure_role(guild: discord.Guild, spec: dict) -> discord.Role:
    role = discord.utils.get(guild.roles, name=spec["name"])
    if role:
        log.info("  · role exists: %s", spec["name"])
        # Update color/hoist/mentionable to match spec
        await role.edit(
            color=spec.get("color", NONE),
            hoist=spec.get("hoist", False),
            mentionable=spec.get("mentionable", False),
            reason="setup_server sync",
        )
        return role
    perms = perms_for(spec["perms"]) if "perms" in spec else discord.Permissions.none()
    role = await guild.create_role(
        name=spec["name"],
        color=spec.get("color", NONE),
        hoist=spec.get("hoist", False),
        mentionable=spec.get("mentionable", False),
        permissions=perms,
        reason="setup_server",
    )
    log.info("  + role created: %s", spec["name"])
    return role


def overwrites_for_category(guild: discord.Guild, visibility: str, role_lookup: dict) -> dict:
    """Build {role: PermissionOverwrite} dict for a category based on visibility band."""
    everyone = guild.default_role
    overwrites = {}

    if visibility == "public":
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)
    elif visibility == "public-readonly":
        # @everyone can browse and react; only @New Shooter+ can post.
        overwrites[everyone] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            add_reactions=True,
            use_application_commands=False,
        )
        for n in ["New Shooter", "Verified Builder", "VIP", "Beta Tester", "Designer", "Mod", "Founder", "Owner", "Partner"]:
            if r := role_lookup.get(n):
                overwrites[r] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_message_history=True,
                    send_messages=True,
                    send_messages_in_threads=True,
                    create_public_threads=True,
                    add_reactions=True,
                    embed_links=True,
                    attach_files=True,
                    use_application_commands=True,
                )
    elif visibility == "members":
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)
        # New Shooter+ can see (everyone with hoisted role above Recruit)
        for n in ["New Shooter", "Verified Builder", "VIP", "Beta Tester", "Designer", "Mod", "Founder", "Owner", "Partner"]:
            if r := role_lookup.get(n):
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)
        # Recruit explicitly denied posting; they only see #welcome + #rules
        if rec := role_lookup.get("Recruit"):
            overwrites[rec] = discord.PermissionOverwrite(view_channel=False)
    elif visibility == "staff":
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)
        for n in ["Mod", "Founder", "Owner"]:
            if r := role_lookup.get(n):
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)
    elif visibility == "founder":
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)
        for n in ["Founder", "Owner"]:
            if r := role_lookup.get(n):
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, read_message_history=True)

    return overwrites


async def ensure_category(guild: discord.Guild, name: str, overwrites: dict) -> discord.CategoryChannel:
    cat = discord.utils.get(guild.categories, name=name)
    if cat:
        log.info("  · category exists: %s", name)
        await cat.edit(overwrites=overwrites, reason="setup_server sync")
        return cat
    cat = await guild.create_category(name=name, overwrites=overwrites, reason="setup_server")
    log.info("  + category created: %s", name)
    return cat


async def ensure_channel(guild: discord.Guild, category: discord.CategoryChannel, spec: dict, role_lookup: dict, category_visibility: str) -> discord.abc.GuildChannel:
    name = spec["name"]
    ch_type = spec["type"]
    existing = discord.utils.get(category.channels, name=name) or discord.utils.get(guild.channels, name=name)
    topic = spec.get("topic", "")
    slowmode = spec.get("slowmode", 0)

    # Build channel-level overwrites: inherit from category, then layer post_role gates
    overwrites = {}
    if "post_role" in spec:
        gate = role_lookup.get(spec["post_role"])
        # Deny send to @everyone in this channel, let only the gate role (+ above) post
        if category_visibility in ("public", "public-readonly"):
            overwrites[guild.default_role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                send_messages_in_threads=False,
                create_public_threads=False,
                create_private_threads=False,
                add_reactions=True,
            )
        else:
            overwrites[guild.default_role] = discord.PermissionOverwrite(
                send_messages=False,
                send_messages_in_threads=False,
                create_public_threads=False,
                create_private_threads=False,
            )
        # Re-allow everyone above the gate to post
        gate_order = ["Recruit", "New Shooter", "Verified Builder", "VIP", "Beta Tester", "Designer", "Mod", "Founder", "Owner"]
        if gate and gate.name in gate_order:
            idx = gate_order.index(gate.name)
            for n in gate_order[idx:]:
                if r := role_lookup.get(n):
                    overwrites[r] = discord.PermissionOverwrite(send_messages=True, send_messages_in_threads=True)

    if existing:
        log.info("  · channel exists: #%s", name)
        if ch_type == "news" and existing.type == discord.ChannelType.text:
            try:
                await existing.edit(type=discord.ChannelType.news, reason="setup_server: convert to Announcement")
                log.info("  · #%s converted to Announcement", name)
            except discord.HTTPException as e:
                log.warning("  ! could not convert #%s to Announcement: %s", name, e)
        if ch_type == "text" or (ch_type == "news" and existing.type in (discord.ChannelType.text, discord.ChannelType.news)):
            try:
                await existing.edit(topic=topic, slowmode_delay=slowmode, overwrites=overwrites or existing.overwrites, reason="setup_server sync")
            except discord.HTTPException:
                pass
        elif ch_type == "forum":
            try:
                await existing.edit(topic=topic, overwrites=overwrites or existing.overwrites, reason="setup_server sync")
            except discord.HTTPException:
                pass
        return existing

    kwargs = {"category": category, "reason": "setup_server"}
    if overwrites:
        kwargs["overwrites"] = overwrites
    if topic:
        kwargs["topic"] = topic
    if slowmode:
        kwargs["slowmode_delay"] = slowmode

    if ch_type == "text":
        ch = await guild.create_text_channel(name, **kwargs)
    elif ch_type == "news":
        kwargs.pop("slowmode_delay", None)
        ch = await guild.create_text_channel(name, **kwargs)
        try:
            await ch.edit(type=discord.ChannelType.news)
        except discord.HTTPException as e:
            log.warning("    could not convert #%s to Announcement (Community feature may not be enabled yet): %s", name, e)
    elif ch_type == "forum":
        kwargs.pop("slowmode_delay", None)
        ch = await guild.create_forum(name, **kwargs)
    elif ch_type == "voice":
        kwargs.pop("topic", None)
        kwargs.pop("slowmode_delay", None)
        ch = await guild.create_voice_channel(name, **kwargs)
    elif ch_type == "stage":
        kwargs.pop("slowmode_delay", None)
        kwargs.pop("topic", None)
        ch = await guild.create_stage_channel(name, **kwargs)
    else:
        raise ValueError(f"unknown channel type: {ch_type}")
    log.info("  + channel created: #%s (%s)", name, ch_type)
    return ch


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            await run_setup(client)
        except Exception:
            log.exception("setup failed")
        finally:
            await client.close()

    await client.start(TOKEN)


async def run_setup(client: discord.Client):
    guild = client.get_guild(GUILD_ID)
    if not guild:
        log.error("Guild %s not found. Is the bot invited to PROJECTKIDCREATIONS?", GUILD_ID)
        return

    log.info("== PROJECTKIDCREATIONS setup beginning ==")
    log.info("Guild: %s (%s)", guild.name, guild.id)

    # Step 1 — roles
    log.info("[1/8] Creating hierarchy roles...")
    role_lookup: dict[str, discord.Role] = {}
    for spec in HIERARCHY_ROLES:
        role_lookup[spec["name"]] = await ensure_role(guild, spec)

    log.info("[2/8] Creating tag/ping roles...")
    for spec in TAG_ROLES:
        role_lookup[spec["name"]] = await ensure_role(guild, {**spec, "perms": "member"})

    # Step 2 — position roles
    log.info("[3/8] Positioning roles in hierarchy...")
    bot_member = guild.me
    bot_top_role = bot_member.top_role
    # Roles managed by integrations (the bot's own role) can't be moved above the bot itself.
    # We'll position user roles below the bot's role.
    try:
        positions = {}
        # Reserve top slot for bot's own integration role (Discord auto-positions it)
        ordered = [r["name"] for r in HIERARCHY_ROLES]
        max_pos = bot_top_role.position - 1
        for i, name in enumerate(ordered):
            role = role_lookup.get(name)
            if role and not role.managed:
                positions[role] = max_pos - i
        if positions:
            await guild.edit_role_positions(positions=positions, reason="setup_server hierarchy")
            log.info("  · role positions updated")
    except (discord.HTTPException, discord.Forbidden) as e:
        log.warning("  ! couldn't reorder roles (bot may need higher position): %s", e)

    # Step 3 — categories + channels (defer stage/news until Community is enabled)
    log.info("[4/8] Creating categories + channels (text/voice/forum first)...")
    category_objs: dict[str, discord.CategoryChannel] = {}
    channel_objs: dict[str, discord.abc.GuildChannel] = {}
    deferred: list[tuple[dict, dict, str]] = []  # (cat_spec, ch_spec, category_visibility)
    for cat_spec in CATEGORIES:
        ovw = overwrites_for_category(guild, cat_spec["visibility"], role_lookup)
        cat = await ensure_category(guild, cat_spec["name"], ovw)
        category_objs[cat_spec["name"]] = cat
        for ch_spec in cat_spec["channels"]:
            if ch_spec["type"] in ("stage", "news"):
                deferred.append((cat_spec, ch_spec, cat_spec["visibility"]))
                continue
            ch = await ensure_channel(guild, cat, ch_spec, role_lookup, cat_spec["visibility"])
            channel_objs[ch_spec["name"]] = ch

    # Step 4 — guild-level settings + Community feature (must come before stage/news)
    log.info("[5/8] Configuring guild settings + Community feature...")
    rules_ch = channel_objs.get("rules")
    updates_ch = channel_objs.get("announcements")
    try:
        await guild.edit(
            verification_level=discord.VerificationLevel.high,
            explicit_content_filter=discord.ContentFilter.all_members,
            default_notifications=discord.NotificationLevel.only_mentions,
            rules_channel=rules_ch,
            public_updates_channel=updates_ch,
            community=True,
            reason="setup_server: enable Community",
        )
        log.info("  · Community feature enabled, verification=High, filter=AllMembers")
    except discord.HTTPException as e:
        log.warning("  ! Community enable failed (may already be enabled or missing prereqs): %s", e)

    # Step 4b — process deferred stage/announcement channels now that Community is on
    log.info("[5b/8] Creating Stage + Announcement channels...")
    for cat_spec, ch_spec, visibility in deferred:
        cat = category_objs[cat_spec["name"]]
        try:
            ch = await ensure_channel(guild, cat, ch_spec, role_lookup, visibility)
            channel_objs[ch_spec["name"]] = ch
        except discord.HTTPException as e:
            log.warning("  ! could not create %s (%s): %s", ch_spec["name"], ch_spec["type"], e)

    # Step 4c — sync channel permissions to category for public-tier channels without
    # post_role gates. This clears any stale @everyone deny overwrites.
    log.info("[5c/8] Syncing channel perms to category for public channels...")
    for cat_spec in CATEGORIES:
        if cat_spec["visibility"] not in ("public", "public-readonly"):
            continue
        cat = category_objs.get(cat_spec["name"])
        if not cat:
            continue
        for ch_spec in cat_spec["channels"]:
            if "post_role" in ch_spec:
                continue  # post-gated channels need their own overwrites
            ch = channel_objs.get(ch_spec["name"])
            if not ch:
                continue
            # If channel is not in the correct category, move it.
            if ch.category_id != cat.id:
                try:
                    await ch.edit(category=cat, sync_permissions=True, reason="setup_server: move + sync")
                    log.info("  · moved #%s to %s and synced perms", ch.name, cat.name)
                    continue
                except discord.HTTPException as e:
                    log.warning("  ! could not move #%s: %s", ch.name, e)
            # Already in correct category: force sync to clear stale overwrites
            try:
                await ch.edit(sync_permissions=True, reason="setup_server: sync to category")
                log.info("  · synced #%s perms to category", ch.name)
            except discord.HTTPException as e:
                log.warning("  ! could not sync #%s: %s", ch.name, e)

    # Step 6 — AutoMod rules
    log.info("[6/8] Creating AutoMod rules...")
    existing_rules = await guild.fetch_automod_rules()
    existing_names = {r.name for r in existing_rules}

    timeout_action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.timeout, duration=timedelta(minutes=10))
    block_action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)

    # Note: timeout action (type 3) is only allowed for keyword/keyword_preset triggers.
    # Spam and mention_spam triggers can only block.
    if "PKC · anti-spam" not in existing_names:
        try:
            await guild.create_automod_rule(
                name="PKC · anti-spam",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
                actions=[block_action],
                enabled=True,
                reason="setup_server",
            )
            log.info("  + automod: anti-spam")
        except discord.HTTPException as e:
            log.warning("  ! anti-spam rule failed: %s", e)

    if "PKC · profanity & slurs" not in existing_names:
        try:
            await guild.create_automod_rule(
                name="PKC · profanity & slurs",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword_preset,
                    presets=discord.AutoModPresets.all(),
                ),
                actions=[block_action],
                enabled=True,
                reason="setup_server",
            )
            log.info("  + automod: profanity & slurs")
        except discord.HTTPException as e:
            log.warning("  ! profanity rule failed: %s", e)

    if "PKC · mention spam" not in existing_names:
        try:
            await guild.create_automod_rule(
                name="PKC · mention spam",
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.mention_spam, mention_limit=5),
                actions=[block_action],
                enabled=True,
                reason="setup_server",
            )
            log.info("  + automod: mention spam")
        except discord.HTTPException as e:
            log.warning("  ! mention-spam rule failed: %s", e)

    # Step 6b — Welcome Screen (required before onboarding can enable)
    log.info("[6b/8] Configuring Welcome Screen...")
    try:
        ws_channels = []
        for name, desc, emoji in [
            ("rules", "Rules of Engagement. Read first.", "📜"),
            ("welcome", "Suit up. Onboarding starts here.", "🎯"),
            ("drops", "Gear drops + product releases.", "🔴"),
            ("showcase", "Show your work.", "🛠️"),
            ("general", "The barracks. Drop in.", "💬"),
        ]:
            ch = channel_objs.get(name)
            if ch:
                ws_channels.append(discord.WelcomeChannel(channel=ch, description=desc, emoji=emoji))
        await guild.edit_welcome_screen(
            description="ENGINEERED REBELLION. New recruit on the range — complete onboarding to enter.",
            welcome_channels=ws_channels,
            enabled=True,
            reason="setup_server",
        )
        log.info("  · welcome screen configured (%d featured channels)", len(ws_channels))
    except discord.HTTPException as e:
        log.warning("  ! welcome screen setup failed: %s", e)

    # Step 7 — Onboarding
    log.info("[7/8] Configuring onboarding...")
    try:
        default_channel_names = ["welcome", "rules", "announcements", "drops", "general", "showcase", "off-topic"]
        default_channels = [channel_objs[n] for n in default_channel_names if n in channel_objs]
        prompts = build_onboarding_prompts(guild)
        # Try enabling. If Discord rejects (some servers need server icon, member count,
        # or a few minutes after Community-enable before onboarding can flip on),
        # fall back to saving prompts as a draft and let the user flip it in UI.
        try:
            await guild.edit_onboarding(
                prompts=prompts,
                default_channels=default_channels,
                enabled=True,
                mode=discord.OnboardingMode.default,
                reason="setup_server",
            )
            log.info("  · onboarding ENABLED with %d prompts", len(prompts))
        except discord.HTTPException as e_enable:
            log.warning("  ! could not auto-enable onboarding (%s) — saving as draft", e_enable)
            await guild.edit_onboarding(
                prompts=prompts,
                default_channels=default_channels,
                enabled=False,
                mode=discord.OnboardingMode.default,
                reason="setup_server: draft",
            )
            log.info("  · onboarding draft saved with %d prompts", len(prompts))
            log.info("  · TO ENABLE: Discord → Server Settings → Onboarding → toggle ON")
    except discord.HTTPException as e:
        log.warning("  ! onboarding setup failed entirely: %s", e)
    except AttributeError:
        log.warning("  ! discord.py version too old for onboarding API (need 2.3+)")

    # Step 8 — Seed #rules + pin welcome embed
    log.info("[8/8] Seeding rules text + welcome embed...")
    rules_ch = channel_objs.get("rules")
    welcome_ch = channel_objs.get("welcome")
    if rules_ch:
        try:
            # Avoid duplicate posts: only seed if channel is empty (no messages from bot yet)
            existing = [m async for m in rules_ch.history(limit=5)]
            if not any(m.author == guild.me for m in existing):
                # Split long rules text if needed (Discord 2000-char limit)
                if len(RULES_TEXT) <= 2000:
                    await rules_ch.send(RULES_TEXT)
                else:
                    # split on blank lines
                    chunks, current = [], ""
                    for line in RULES_TEXT.split("\n"):
                        if len(current) + len(line) + 1 > 1900:
                            chunks.append(current)
                            current = line + "\n"
                        else:
                            current += line + "\n"
                    if current:
                        chunks.append(current)
                    for chunk in chunks:
                        await rules_ch.send(chunk)
                log.info("  · #rules seeded")
            else:
                log.info("  · #rules already has bot messages, skipping seed")
        except discord.HTTPException as e:
            log.warning("  ! could not seed #rules: %s", e)

    if welcome_ch:
        try:
            existing = [m async for m in welcome_ch.history(limit=10)]
            already_pinned = any(m.author == guild.me and m.pinned for m in existing)
            if not already_pinned:
                msg = await welcome_ch.send(embed=build_welcome_embed())
                try:
                    await msg.pin()
                except discord.HTTPException:
                    pass
                log.info("  · welcome embed pinned in #welcome")
            else:
                log.info("  · welcome embed already pinned, skipping")
        except discord.HTTPException as e:
            log.warning("  ! could not seed #welcome: %s", e)

    log.info("== PROJECTKIDCREATIONS setup complete ==")
    log.info("Server is ready. Hop into Discord and verify.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Cancelled.")
