# FAQ — #server-guide thread 7

**Thread title:** `FREQUENTLY ASKED QUESTIONS.`
**Tags:** `faq`, `navigation`
**Color:** `#3F4448` (anodized slate)

---

## ROLE PROGRESSION

**Q: How do I become an @New Shooter?**
A: Two paths. (1) Reach Top Shooter Level 20 by chatting — about a thousand messages over weeks. The bot grants @New Shooter automatically. (2) A @Mod manually promotes you if they see sustained contribution before you hit Level 20. There's no application process for either.

**Q: How long does it take to hit Level 20?**
A: With a normal pace of 5–20 messages per day, expect 6–12 weeks. The level system has a 60-second per-user cooldown on XP gain, so spamming doesn't help.

**Q: How do I become @Verified Builder?**
A: Complete the standing build challenge. Spec is in `#server-guide` → **Build Pipeline**, Stage 6. You submit photos of the PKC reference build in `#build-help` with a `[VERIFY]` prefix; a Mod reviews within 7 days.

**Q: How do I become @VIP?**
A: Support PKC financially — Patreon subscription, Ko-fi tips, or hit a $100+ lifetime spend in the PKC store. Until the auto-sync integration ships, DM a @Mod with proof of support and they'll grant the role manually.

**Q: How do I become @Beta Tester?**
A: First earn @Verified Builder. Then DM a @Mod when a beta cycle opens — staff announces openings in `#announcements` every drop cycle. Beta cohorts are small (10–20 members). Rotation is at staff discretion.

**Q: Why can't I post in #general yet?**
A: `#general` requires @New Shooter. New joins are @Recruit and can only post in `#off-topic` until they earn @New Shooter (via Level 20 or mod promotion). This is the gate that filters drive-by accounts from real community members.

**Q: Can I lose a role?**
A: Yes. @New Shooter can be revoked for rule violations. @Verified Builder is permanent except for piracy / safety rule breaks. @VIP expires if your supporting subscription lapses (30-day grace period). Hierarchy roles (@Mod, @Founder, @Owner) are step-down on departure.

---

## NAVIGATION (WHERE-TO-POST)

**Q: I built something cool. Where do I post it?**
A: `#showcase`. One post per build. Tag what you're running. If you printed the file from PKC, link the source `#print-files` thread.

**Q: My print is failing. Where do I get help?**
A: `#build-help`. Be specific: photos, print settings, material, what you tried. Vague help requests get vague answers.

**Q: I want to share an STL I made. Where does that go?**
A: `#print-files`, but you need @Verified Builder to create threads there. Until you have that, post in `#mod-talk` discussing the design — once you're verified, you can post the file properly.

**Q: Where do I see what's dropping next?**
A: Watch `#drops`. Pick up `Pings · Drops` in onboarding (or via the role panel later) to get notified when a drop is announced (48h before drop day). Drop teasers in `#drops-pipeline` are staff-only by design.

**Q: I want to chat but I'm a new member. Where can I talk?**
A: `#off-topic` is the only channel chattable for @Recruit. Drop in there, introduce yourself, hang out. Once you earn @New Shooter, the rest of `#community` opens up.

**Q: Where's the PKC store / website?**
A: `projectkidcreations.io`. Linked in the server's About section and in onboarding.

---

## MOD CONTACT + COMPLIANCE

**Q: How do I contact a mod?**
A: Three tiers (see `#server-guide` → **Mod Contact**): react with 🚩 on a problem message (low-urgency), use `/report` slash command (medium), DM the @Mod role directly (high-urgency, private). For ban appeals on permanent bans, email **appeals@projectkidcreations.io**.

**Q: I was banned and want to appeal.**
A: Email **appeals@projectkidcreations.io** with your Discord username, ID, the reason given, and your case. Founder reviews monthly. Most permanent bans stick. Ban evasion (alt accounts) makes the ban permanent.

**Q: Someone is harassing me. What do I do?**
A: (1) Block them on Discord (right-click → Block). (2) Report to PKC mods via DM with screenshots — the @Mod role is DM-reachable. (3) If it's Discord-TOS-level (threats, doxxing, illegal content), report to Discord directly via the message right-click menu. PKC mods can ban from PKC; Discord can ban from the platform.

**Q: Can I share files I didn't make?**
A: Only if you have rights or it's already open-source. **Don't** post pirated STLs, leaked PKC files, or files from other designers without permission. Rule 05. We protect designers — including the ones outside PKC.

**Q: Can I advertise my own stuff?**
A: No DM advertising. No link-spamming. No follow-for-follow. If you want a partnership, DM a @Mod and they'll route to `#partnerships` (staff-only). Rule 06.

**Q: NSFW content?**
A: Not on this server, ever. 14+ baseline, with 18+ marketing surfaces gated by role. Rule 07. No NSFW in any channel.

---

## BRAND + BOT

**Q: What does "Engineered Rebellion" actually mean?**
A: Two-word brand thesis. **Engineered**: PKC files are designed to spec, dimensioned, documented, and tested — not hacked together. **Rebellion**: PKC's open-file model is a refusal of the buy-only mainstream gel-blaster market. Read the full thesis in `#server-guide` → **Brand Story**.

**Q: Who founded PKC?**
A: PK Blick is the founder. See `#server-guide` → **History** for the founder note.

**Q: What's Top Shooter?**
A: PKC's custom Discord bot. Handles XP/leveling, moderation, audit logging, welcomes, role assignments, the temp-voice system, and more. See the `bot.py` source if you want the internals — the project is open. `/help` in `#bot-commands` to see live commands.

**Q: What bots run here?**
A: One: Top Shooter (PKC's own). No third-party bots. Discord's built-in AutoMod runs alongside it for keyword/slur/spam filtering.

**Q: Can I run my own bot in this server?**
A: No third-party bot integrations are added without staff approval. If you've built something useful, DM a @Mod and pitch it.

**Q: Where's the bot's source code?**
A: Not public yet. May open up post-v1.0 of the bot. The server-build script (`setup_server.py`) lives in the PKC project directory and is reproducible.

---

## MISCELLANEOUS

**Q: I have a feature request for the server / bot.**
A: Post in `#off-topic` (if you're @Recruit) or `#general` (if @New Shooter+). Staff watches both. For a formal proposal, DM a @Mod with the spec.

**Q: I want to host an event here.**
A: PKC events are staff-organized for now. If you have an event idea (range meetup, build-along, AMA with a designer), DM a @Mod. Approved events get a Stage channel slot or scheduled event.

**Q: How do I leave the server?**
A: Right-click the PROJECTKIDCREATIONS icon in the server list → Leave Server. We're sorry to see you go. The door's open if you come back.

**Q: Does PKC sell to my country?**
A: Check `projectkidcreations.io` for current shipping zones. Files are global; physical kits are limited to certain regions per local law on gel-blaster import.

---

**Version:** v0.1 · 2026-05-14
