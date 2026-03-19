#!/usr/bin/env python3
"""
Generate UI illustrations for DotMac ERP using Google Gemini API.

Usage:
    python scripts/generate_illustrations.py --api-key YOUR_KEY
    # or set GEMINI_API_KEY env var
    GEMINI_API_KEY=your_key python scripts/generate_illustrations.py

Generates consistent illustrations for empty states, module selector,
login page, and error pages. Saves to static/img/illustrations/.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "illustrations"

# Consistent brand style prefix for all prompts
STYLE_PREFIX = (
    "Minimal flat illustration, clean vector style, soft gradients. "
    "Primary color: teal (#0d9488). Accent color: warm gold (#d97706). "
    "Secondary: soft slate gray (#94a3b8). "
    "White/transparent background. No text, no words, no labels, no watermarks. "
    "Subtle shadow beneath main element. "
    "Modern, professional, friendly — like Notion or Linear empty states. "
    "Simple composition, centered subject, plenty of negative space. "
)

# Each illustration: (filename, prompt_suffix, description)
ILLUSTRATIONS: list[tuple[str, str, str]] = [
    (
        "empty-invoices.png",
        "A single elegant document page with a subtle teal checkmark, "
        "floating slightly above a soft shadow. A small gold coin beside it. "
        "Conveys: no invoices yet, ready to create one.",
        "Empty state: No invoices",
    ),
    (
        "empty-transactions.png",
        "A minimalist bank card with gentle teal gradient, "
        "with three small horizontal lines suggesting transaction rows that fade out. "
        "A subtle sparkle on the card corner. "
        "Conveys: no transactions yet.",
        "Empty state: No transactions",
    ),
    (
        "empty-employees.png",
        "Three abstract person silhouettes (head + shoulders) in varying sizes, "
        "the center one teal, flanking ones in light slate gray. "
        "Gentle overlap. Conveys: no team members added yet.",
        "Empty state: No employees",
    ),
    (
        "empty-inventory.png",
        "An open cardboard box viewed from slight above angle, "
        "with a teal glow inside suggesting emptiness with potential. "
        "A small gold tag hanging from the side. "
        "Conveys: empty warehouse, ready to stock.",
        "Empty state: No inventory items",
    ),
    (
        "empty-claims.png",
        "A receipt or expense slip with a dotted outline, "
        "a small teal circular arrow suggesting submission flow. "
        "A tiny gold coin stack beside it. "
        "Conveys: no expense claims submitted.",
        "Empty state: No expense claims",
    ),
    (
        "empty-search.png",
        "A magnifying glass with teal-tinted lens, "
        "looking at empty space with subtle dotted circles radiating outward. "
        "Conveys: search returned no results.",
        "Empty state: No search results",
    ),
    (
        "getting-started.png",
        "A small teal rocket launching upward from a gold launchpad, "
        "with a gentle curved trail. Minimal cloud wisps. "
        "Conveys: getting started, first launch, onboarding.",
        "Onboarding: Getting started",
    ),
    (
        "error-404.png",
        "A compass with the needle pointing to a question mark, "
        "teal compass body with gold needle and accents. "
        "Slightly tilted. Conveys: lost, page not found.",
        "Error: 404 page not found",
    ),
    (
        "empty-reports.png",
        "A minimal bar chart with three bars of different heights, "
        "in teal with the tallest bar having a gold accent cap. "
        "A subtle grid behind. Conveys: no report data yet.",
        "Empty state: No reports",
    ),
    (
        "empty-approvals.png",
        "A clipboard with a single checkbox, unchecked, "
        "with a teal pen resting diagonally across it. "
        "Gold clip at the top. Conveys: no pending approvals.",
        "Empty state: No pending approvals",
    ),
    # =========================================================================
    # BATCH 2: Module selector cards (12 illustrations)
    # Used on the module selector page (/) — each module gets a branded icon
    # Style: slightly larger, more detailed than empty states, square format
    # =========================================================================
    (
        "module-finance.png",
        "A thick leather-bound ledger book, slightly open, "
        "with teal bookmark ribbon and gold page edges. "
        "A small coin stack beside it. Clean, iconic, centered.",
        "Module: Finance",
    ),
    (
        "module-ar.png",
        "A stack of three invoices/documents fanning out, "
        "emerald green (#059669) tint on the top document with a checkmark seal. "
        "A small upward arrow indicating incoming money. Clean, iconic.",
        "Module: Accounts Receivable",
    ),
    (
        "module-ap.png",
        "A single bill/invoice with a rose (#e11d48) stamp mark saying 'PAID', "
        "a small outward arrow indicating payment going out. "
        "Clean, iconic, centered.",
        "Module: Accounts Payable",
    ),
    (
        "module-banking.png",
        "A modern bank building facade, minimal and geometric, "
        "blue (#2563eb) tinted with a vault door circle motif. "
        "Small currency symbols floating. Clean, iconic.",
        "Module: Banking",
    ),
    (
        "module-people.png",
        "Four diverse person silhouettes (head + shoulders) in a semi-circle, "
        "violet (#8b5cf6) as primary color, slightly overlapping. "
        "A small heart or handshake above them. Warm, inclusive.",
        "Module: People/HR",
    ),
    (
        "module-inventory.png",
        "Warehouse shelves in perspective view, two rows deep, "
        "amber (#d97706) accent on box labels and shelf edges. "
        "Neatly organized boxes. Clean, iconic.",
        "Module: Inventory",
    ),
    (
        "module-expense.png",
        "An open wallet with receipt papers poking out, "
        "amber (#f59e0b) accent. A small calculator beside it. "
        "Clean, iconic, centered.",
        "Module: Expenses",
    ),
    (
        "module-procurement.png",
        "Two hands in a handshake with a contract document behind, "
        "blue (#2563eb) tinted. A small checkmark seal on the contract. "
        "Professional, clean, iconic.",
        "Module: Procurement",
    ),
    (
        "module-projects.png",
        "A Kanban board with three columns and colorful task cards, "
        "teal column headers, gold highlight on one card. "
        "Clean, minimal, top-down view.",
        "Module: Projects",
    ),
    (
        "module-public-sector.png",
        "A classical government building with columns, "
        "cyan (#0891b2) tinted, with a flag on top. "
        "A budget pie chart motif in the foreground. Clean, iconic.",
        "Module: Public Sector",
    ),
    (
        "module-support.png",
        "A headset with a speech bubble containing a checkmark, "
        "teal headset with gold accent on the bubble. "
        "Clean, iconic, centered, friendly.",
        "Module: Support",
    ),
    (
        "module-coach.png",
        "A glowing lightbulb with a small upward growth chart line inside it, "
        "purple (#a855f7) glow around the bulb, gold filament. "
        "Conveys: AI insights, recommendations.",
        "Module: Coach",
    ),
    # =========================================================================
    # BATCH 3: Login, error pages, onboarding (5 illustrations)
    # =========================================================================
    (
        "login-hero.png",
        "A modern workspace scene: a laptop showing a dashboard with teal charts, "
        "a coffee cup beside it, a small plant, and soft morning light coming from the left. "
        "Warm, inviting, professional. Slightly wider composition (not square). "
        "Isometric or slight 3D perspective. No text on the screen.",
        "Login: Hero illustration",
    ),
    (
        "error-500.png",
        "A cute robot with a wrench, looking apologetic with a small sweat drop. "
        "Teal robot body with gold wrench. A gear with a crack in it nearby. "
        "Conveys: something broke, we're fixing it. Friendly, not scary.",
        "Error: 500 server error",
    ),
    (
        "error-403.png",
        "A padlock with a keyhole, teal lock body with gold keyhole. "
        "A small 'no entry' circle overlaid subtly. "
        "Conveys: access denied, you don't have permission.",
        "Error: 403 forbidden",
    ),
    (
        "onboarding-welcome.png",
        "A person stepping through an open door into a bright room, "
        "teal door frame, gold light streaming through. "
        "Path of stepping stones leading to the door. "
        "Conveys: welcome, new beginning, first day.",
        "Onboarding: Welcome",
    ),
    (
        "maintenance.png",
        "A traffic cone with a teal hard hat resting on top, "
        "gold caution stripes on the cone. Small wrench and screwdriver crossed behind. "
        "Conveys: under maintenance, be right back.",
        "Maintenance mode",
    ),
    # =========================================================================
    # BATCH 4: Dashboard heroes (6 illustrations)
    # Wider, more atmospheric, used as subtle background accents
    # =========================================================================
    (
        "hero-finance.png",
        "An abstract financial landscape: ascending bar chart bars "
        "transitioning into a city skyline silhouette. Teal gradient with gold highlights. "
        "Very minimal, almost like a decorative border. Wide composition.",
        "Dashboard hero: Finance",
    ),
    (
        "hero-people.png",
        "Abstract connected circles representing a team network/org chart, "
        "violet (#8b5cf6) nodes with gentle connecting lines. "
        "Some nodes slightly larger (managers). Organic layout. Wide.",
        "Dashboard hero: People",
    ),
    (
        "hero-expense.png",
        "Abstract flowing receipt tape curving across the frame, "
        "amber (#f59e0b) gradient, with small coin dots scattered along the path. "
        "Minimal, decorative. Wide composition.",
        "Dashboard hero: Expense",
    ),
    (
        "hero-inventory.png",
        "Abstract warehouse grid viewed from above, "
        "emerald (#10b981) pallet squares in an organized grid with one amber highlighted. "
        "Minimal, pattern-like. Wide composition.",
        "Dashboard hero: Inventory",
    ),
    (
        "hero-banking.png",
        "Abstract flowing line chart representing cash flow, "
        "blue (#2563eb) line with teal fill beneath. Gold dots at peaks. "
        "Smooth, calming, data-visualization feel. Wide.",
        "Dashboard hero: Banking",
    ),
    (
        "hero-procurement.png",
        "Abstract supply chain flow: three circles connected by arrows, "
        "blue (#3b82f6) circles with teal arrows between them. "
        "Representing order → delivery → receipt. Minimal, wide.",
        "Dashboard hero: Procurement",
    ),
    # =========================================================================
    # BATCH 5: Help center & email headers (5 illustrations)
    # =========================================================================
    (
        "help-learning.png",
        "An open book with pages turning, a lightbulb floating above it, "
        "teal book cover, gold lightbulb glow. Small graduation cap nearby. "
        "Conveys: learning, knowledge, training.",
        "Help: Learning center",
    ),
    (
        "help-video.png",
        "A play button triangle inside a rounded rectangle screen, "
        "teal play button, gold progress bar beneath. "
        "Conveys: video tutorial, watch and learn.",
        "Help: Video tutorial",
    ),
    (
        "help-guide.png",
        "A numbered list (1, 2, 3) with small checkmarks, "
        "teal numbers, gold checkmarks. Steps laid out vertically. "
        "Conveys: step-by-step guide, how-to.",
        "Help: Step-by-step guide",
    ),
    (
        "email-header-finance.png",
        "A minimal teal banner with a small ledger/document icon on the left "
        "and a subtle gold accent line. Very wide and short (banner proportions). "
        "Professional, branded header for finance emails.",
        "Email header: Finance",
    ),
    (
        "email-header-hr.png",
        "A minimal violet (#8b5cf6) banner with a small people icon on the left "
        "and a subtle gold accent line. Very wide and short (banner proportions). "
        "Professional, branded header for HR emails.",
        "Email header: HR",
    ),
]


def generate_illustration(
    client: genai.Client,
    filename: str,
    prompt_suffix: str,
    description: str,
    output_dir: Path,
    model: str = "gemini-2.5-flash-preview-05-20",
) -> bool:
    """Generate a single illustration and save it."""
    output_path = output_dir / filename

    if output_path.exists():
        logger.info("  SKIP %s (already exists)", filename)
        return True

    full_prompt = STYLE_PREFIX + prompt_suffix

    logger.info("  Generating %s — %s", filename, description)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[full_prompt],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image = part.as_image()
                image.save(str(output_path))
                logger.info(
                    "  SAVED %s (%s bytes)", filename, output_path.stat().st_size
                )
                return True

        logger.warning("  WARN %s — no image in response", filename)
        return False

    except Exception as e:
        logger.error("  FAIL %s — %s", filename, e)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DotMac ERP illustrations")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    parser.add_argument("--model", default="gemini-2.5-flash-preview-05-20")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--only", help="Generate only this filename")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    if not args.api_key:
        logger.error("Set GEMINI_API_KEY or pass --api-key")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=args.api_key)

    illustrations = ILLUSTRATIONS
    if args.only:
        illustrations = [(f, p, d) for f, p, d in ILLUSTRATIONS if f == args.only]
        if not illustrations:
            logger.error("No illustration named '%s'", args.only)
            sys.exit(1)

    if args.force:
        for filename, _, _ in illustrations:
            path = args.output_dir / filename
            if path.exists():
                path.unlink()

    logger.info(
        "Generating %d illustrations → %s\n", len(illustrations), args.output_dir
    )

    success = 0
    for i, (filename, prompt_suffix, description) in enumerate(illustrations):
        if generate_illustration(
            client, filename, prompt_suffix, description, args.output_dir, args.model
        ):
            success += 1

        # Rate limiting — be polite to the free tier
        if i < len(illustrations) - 1:
            time.sleep(2)

    logger.info("\nDone: %d/%d generated", success, len(illustrations))


if __name__ == "__main__":
    main()
