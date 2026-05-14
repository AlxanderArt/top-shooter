# Build Pipeline — #server-guide thread 4

**Thread title:** `BUILD PIPELINE — FROM FILE TO FIELD.`
**Tags:** `builds`, `verification`
**Color:** `#FF5F1F` (hi-vis orange)

---

How a build moves through the PKC system: from picking up a file, to printing, to dialing in, to showcasing, to earning @Verified Builder.

## STAGE 1 — PICK UP THE FILE

Files live in **`#print-files`** (Forum channel). Each thread is one build.

**What you'll find in a thread:**
- File link (STL / 3MF / STEP, sometimes Fusion source)
- Print settings: layer height, infill %, supports, orientation
- Material recommendations (PETG for chassis, ASA for outdoor, ABS for hot environments, etc.)
- Post-process notes (sand to grit, paint stack, livery references)
- Build photos from the original poster
- Print reports from members who've replicated it

**File sources:**
1. **PKC official drops** — uploaded by @Designer or @Mod. Tagged `PKC-Official`. Always free or paid depending on the drop tier.
2. **Verified Builder uploads** — community designs, vetted. Tagged `Open-Source` or `Verified Builder`.
3. **Remix uploads** — modifications of existing PKC files. Tagged `Remix · Source: <original>`.

Only @Verified Builder+ can create new threads in `#print-files`. Anyone @New Shooter+ can comment.

## STAGE 2 — PRINT

This is on you. PKC doesn't run a print farm.

**Recommended settings (chassis files):**
- Layer height: 0.20mm (chassis) / 0.12mm (high-detail parts)
- Infill: 25% gyroid (structural) / 40% (high-stress mounts)
- Walls: 4 (load-bearing) / 3 (cosmetic)
- Material: PETG default. ASA for outdoor. PA-CF if you have the printer for it.
- Orientation: parts are oriented in-source for strength — don't reorient unless you have a reason.
- Supports: tree supports, 50° threshold. Brim for narrow contact patches.

These are starting points. Each file has its own settings in the thread.

## STAGE 3 — POST-PROCESS

- Sand to 220 grit for paint.
- Acetone-vapor smoothing on ABS (in a vented setup, eye-pro on).
- Primer + livery. PKC's reference liveries: tactical-black base + hi-vis-orange accents (60/20/10 ratio), or full anodized-slate.
- Decals: PKC watermark stamp on every published build. Mods provide the SVG. DM a @Mod for the file.

## STAGE 4 — DIAL IN

Range-test it before posting to `#showcase`.

- Fitment check: does it mate cleanly with the gel-blaster receiver / chassis it's designed for?
- Stress check: dry-fire cycle. Look for flex, cracks, threads stripping.
- Field test: actual range use. 100+ rounds minimum.

If it fails, post in `#build-help` with photos. Don't ghost-post broken builds to `#showcase`.

## STAGE 5 — SHOWCASE

Post your finished build in **`#showcase`**.

**Showcase post format:**
- 1–4 photos (well-lit, full build + detail shots).
- Build name + base platform.
- Material + livery callouts.
- Source thread link (`#print-files` thread the file came from).
- Print report: settings deviations, what worked, what didn't.

Don't repost the file in `#showcase` — link the `#print-files` thread instead.

## STAGE 6 — EARN @VERIFIED BUILDER

**The standing PKC build challenge.**

To earn @Verified Builder, you must build the **PKC reference kit** and submit photos for staff review.

### Current challenge spec (v0.1)

> **Build:** PKC reference chassis (Mk1 carbine pattern).
> **File:** Posted in `#print-files` under the tag `Verification Challenge`. File link will be the canonical drop when v1 lands; until then, message a @Mod to receive the verification kit.
> **Livery:** Must include the PKC brand combo — tactical-black `#0A0A0A` base with hi-vis-orange `#FF5F1F` accents at the 70/20/10 ratio. Custom livery is fine, but the brand combo must be present somewhere on the build.
> **Material:** Any. Print quality is judged on fitment and finish, not on filament cost.
> **Photos:** Minimum 4 photos — full build (left, right, front), one detail shot. Must include the PKC watermark decal in at least one photo.
> **Submission:** Post in `#build-help` with a `[VERIFY]` prefix in your first message. Tag the thread `Verification Submission`. A @Mod reviews within 7 days.
> **Pass criteria:** Functional build, clean fitment, brand combo present, watermark visible, no major print defects (zits, layer separation, support scarring on visible surfaces).
> **Fail:** Mods leave a comment with specifics. You can re-submit any time.

Pass → @Verified Builder role granted within 24h of mod review.

### Why a challenge

The challenge is the bar that says: this member can actually print PKC files to spec. Once you've done it, you're trusted to create new threads in `#print-files`. The challenge protects the maker zone from spam files and bad prints.

You only do this once. The role is permanent (unless revoked for rule violations).

## STAGE 7 — KEEP BUILDING

Once you're @Verified Builder:

- Post your own builds to `#print-files` as new threads.
- Eligible for `Build Stream Pings` to get notified when staff hosts live build walkthroughs.
- Eligible to apply for @Beta Tester — DM a @Mod when a beta cycle opens.
- Feature priority in `#showcase` highlight rotations.
- Voting weight in occasional community decisions (e.g., next-chassis polls).

---

**Version:** v0.1 · 2026-05-14
