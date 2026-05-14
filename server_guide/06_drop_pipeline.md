# Drop Pipeline — #server-guide thread 5

**Thread title:** `DROP PIPELINE — HOW RELEASES WORK.`
**Tags:** `drops`, `release-cycle`
**Color:** `#FF1F1F` (alarm red — drop-day urgency)

---

PKC ships drops on a **monthly calendar** with a **three-stage rollout**: Beta Tester preview → VIP early access → public release. Drops are **time-boxed** — once the window closes, the drop is closed (with rare restocks). This is by design. The brand operates on limited-edition mechanics; the calendar makes them predictable.

## THE CALENDAR

| Day of cycle | Stage | Who has access |
|---|---|---|
| Day 0 | Drop teaser in `#drops-pipeline` (staff-only) | Staff |
| Day -7 (one week before public) | Beta Tester preview goes live | @Beta Tester |
| Day -1 (24h before public) | VIP early access opens | @VIP + @Beta Tester |
| **Day 0 (drop day)** | **Public release in `#drops`** | **All members** |
| Day 0 + N | Drop closes (varies — typically 48h to 14 days, announced per drop) | — |

Drop day is announced **48 hours in advance** via a ping to `Pings · Drops` in `#drops`. The announcement includes:

- Drop name + product category
- Exact drop time (timezone-aware)
- Availability window length
- Whether it's a limited file release, paid kit, or free open release
- Pricing tier (if paid)

## STAGE 1 — TEASER (Day 0 in staff)

Staff drops a teaser image, working title, and rough specs into `#drops-pipeline` (staff-only). The team finalizes pricing, availability, file packaging, and livery references. **You won't see this stage as a member.** Stop asking what's next — drops stay quiet on purpose.

## STAGE 2 — BETA TESTER PREVIEW (Day -7)

@Beta Tester members get the drop **7 days before public release**.

- Access via a hidden thread in `#drops` (made visible to @Beta Tester only).
- Includes the file or the kit pre-order page.
- **Required**: Beta Testers submit feedback within 5 days via the thread.
  - Print report (settings used, what worked, what didn't, fitment issues)
  - At least one photo
  - Suggested fixes for v1.1 of the file (if applicable)
- Feedback is incorporated into the public release files when possible. If a major flaw is found, the public release is delayed and the calendar shifts.

**Why this exists:** Catching bugs before the public sees them. Beta is a working role, not a perk.

## STAGE 3 — VIP EARLY ACCESS (Day -1)

@VIP members get the drop **24 hours before public release**.

- Files / pre-orders open one day early.
- Limited drops (low-stock paid kits) often sell out in the VIP window — that's part of the value of being VIP.
- Open files (free STL drops) are available to VIP one day early as a thank-you for support; the public still gets them at Day 0.

**Why this exists:** VIP supports the brand financially. Early access is the structural acknowledgment.

## STAGE 4 — PUBLIC RELEASE (Day 0)

The full announcement posts in `#drops`. `Pings · Drops` is pinged. The drop is now visible to everyone.

What the post contains:

- Drop name + the brand drop number (PKC drops are numbered: `DROP-001`, `DROP-002`, …)
- Hero photo (livery reference)
- File link (if free) or product page (if paid)
- Specs + print settings (for printable drops)
- Pricing tier (if paid)
- Availability window — when the drop closes
- Compatible platforms (Glock-pattern, M4-pattern, etc.)
- Reference build photos from staff + Beta Testers

`#drops` is an **Announcement channel** — other servers can follow it to mirror PKC drops into their own communities. If you run a server and want to mirror, click the bell icon in the channel and follow.

## STAGE 5 — DROP CLOSES

After the announced window, the drop is **closed**.

- Paid kits: no longer purchasable. Sometimes a single restock 60–90 days later if there's enough demand. Restocks are announced in `#announcements`.
- Free files: stay available indefinitely in `#print-files`. The drop closing only means the *announcement cycle* ends — the file itself remains in the catalog.

Closed drops are tagged `Closed` in the original `#drops` post. The post stays up as a historical record.

## DROP TYPES

PKC ships several drop formats. Each has its own conventions.

### Open File Drop
- Free STL / 3MF.
- Tagged `Open-Source` in `#print-files`.
- Public benefit: anyone can print without paying.
- Posted in `#drops` as a release, but the file is in `#print-files` permanently.

### Paid Kit Drop
- Physical product or paid file bundle.
- Pricing tier shown.
- Limited availability typical.
- VIP early access matters here — paid kits often sell out before they hit public.

### Build-Along Release
- Drops as a file + a coordinated "build week" event in `PKC Stage`.
- Members print together over 7 days. Daily check-ins via stream or stage.
- @Verified Builders who complete the build-along on time are eligible for a prize (announced per build-along).
- Run quarterly at most.

### Mod / Aftermarket Drop
- Sub-category. Smaller accessory pieces (mag adapters, rail mounts, optic mounts).
- Lighter cycle: sometimes just a 24h public window with no Beta / VIP early access.
- Get pinged via `Pings · Mod Drops`.

## NOTIFICATIONS

To get pinged on drops, pick up the relevant ping role:

- `Pings · Drops` — every drop, all formats.
- `Pings · Mod Drops` — mod / aftermarket drops only.
- `Pings · Build Streams` — Build-along drops + live build streams in PKC Stage.

Pick these up via the onboarding flow on join, OR via the role panel (Discord client → right-click your name → Edit Roles, or use the upcoming `/roles` slash command).

To unsubscribe: pick up `Pings · Silent` (opts you out of all ping roles).

---

**Version:** v0.1 · 2026-05-14
