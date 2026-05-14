# Roadmap — #server-guide thread 10

**Thread title:** `ROADMAP — WHERE THIS IS GOING.`
**Tags:** `roadmap`, `vision`
**Color:** `#39FF14` (neon green — earned-state, forward-looking)

---

PKC's roadmap is **vision-level, not calendar-level**. Drops and product specifics stay quiet by design (limited-edition mechanics depend on it). What we publish here is **direction** — what categories of work are on the horizon, in priority order.

This document gets updated as priorities shift. Each section is honest about whether it's actively in flight, queued for the next 6 months, or aspirational. **No dates** — only ranks.

---

## ACTIVELY IN FLIGHT

These are being worked on right now. They will land, in some form, in the foreseeable future.

### Mk-series chassis expansion
The first PKC chassis (Mk1, carbine-pattern) is the verification-challenge baseline. Mk2 and beyond will expand the chassis catalog: different platforms, different roles (DMR, PDW, custom). Each Mk is its own drop cycle.

### Top Shooter bot — feature buildout
Top Shooter is shipped in phases. Phase 0 (online) is live. The phases on deck:
- Phase 1: UI components — buttons, modals, dropdowns. Live demos via `/demo`.
- Phase 2: SQLite persistence layer.
- Phase 3: Moderation cog (kick / ban / timeout / warn).
- Phase 4: Audit logging cog.
- Phase 5: Welcome / leave messages.
- Phase 6: Auto-role + reaction roles.
- Phase 7: Levels + XP (the @New Shooter gate depends on this).
- Phase 8: AutoMod cog with regex filters.
- Phase 9: Channel management.
- Phase 10: Temp voice channels (the `+ NEW VOICE` trigger depends on this).

Each phase ships as a stable cog. The whole bot grows in the open.

### Open-file catalog
Maintained library of PKC open files in `#print-files`, tagged, searchable, organized. Some are PKC-official; some are Verified Builder community contributions. Goal: when a member asks "what files are available," the answer is "open `#print-files` and filter by tag."

---

## QUEUED — NEXT WAVE

Beyond active work but on the priority list. These will likely land in the next 6 months.

### Material lineup expansion
Recommendations and proven-in-the-field calibration for more materials: PA-CF, PC-CF, glass-filled blends. PKC publishes settings per chassis per material, building a calibration matrix.

### Range event series
Coordinated in-person PKC meetups in select regions. Members RSVP, get `Pings · Range Meetups`, show up with their builds. Started small — one region, then expanding.

### Build database
Searchable index of community builds across `#showcase`. Filter by chassis, material, livery, contributor. Doubles as inspiration and as a print-report library. May live in a thread index or as an external static site referenced from `#server-guide`.

### Affiliate / partner program
Formal affiliate program for Partners who promote PKC drops in their own communities. Includes commission structure, drop-tracking, and dedicated `#partnerships` workflow.

### Live build streams
Regular use of `PKC Stage` for live builds, designer Q&A, drop reveals. Built on top of the existing Stage channel — we just need to find the right cadence.

---

## ASPIRATIONAL — LONGER-TERM

These are the brand's long arc. Not promised, not scheduled, but they're where PKC is pointed.

### Multi-platform chassis ecosystem
PKC chassis files for every major gel-blaster platform — not just M4 / Glock derivatives, but DMR builds, sub-compacts, sniper-pattern, designated-marksman builds. A full PKC catalog that lets a maker run PKC-design from any base platform.

### Open-source design system + community remixes
The PKC design system is currently brand-owned. Long-term: open the design tokens, the figma spec, the type rules — so community designers can produce PKC-compliant content (livery designs, drop graphics, range posters) without needing brand-team approval.

### Tactical accessory line
Beyond chassis: holsters, slings, pouches, modular load-bearing gear. 3D-printable where possible, sewn where required. Tagged as a sub-category of drops.

### Educational content
PKC-published guides: "Print a chassis from zero," "Tune a gel-blaster build," "Run a range day." Living curriculum for makers entering the space.

### Brand partnerships
Selective partnerships with adjacent brands — material vendors (filament partnerships), printer manufacturers (calibration recipes), event organizers. Limited and curated.

### Community-owned events
Range events run by Verified Builders rather than only by staff. PKC provides the structure (brand, sponsorship, ping support); community runs the day-of execution.

---

## EXPLICITLY NOT ON THE ROADMAP

To save you the question:

- **Real-firearm anything.** PKC is gel-blaster only and always will be.
- **NFTs, crypto, "Web3" integrations.** Not in our future.
- **Closing the open-file path.** The file-first thesis is the brand. We will never go buy-only.
- **Public bot source release before v1.0.** Top Shooter is open-by-default eventually, but the v0.x phases are too unstable to publish cleanly. Will reconsider at v1.0.

---

This roadmap will be revised as priorities evolve. If something on this list matters to you specifically — DM a @Mod or post in `#general` (when you're @New Shooter+). Staff watches.

---

**Version:** v0.1 · 2026-05-14
