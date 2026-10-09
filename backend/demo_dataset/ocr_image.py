"""A synthetic scanned notice for the OCR demo (Part 9).

Rendered with Pillow's bundled font, word by word with explicit gaps (so OCR keeps word
boundaries), so the image is deterministic and needs no system fonts or external files.
"""

from __future__ import annotations

import io

from uuid import UUID

from demo_dataset.spec import demo_id


OCR_DEMO_FILENAME = "Facilities_Notice_Scan.png"
OCR_DEMO_DOCUMENT_ID: UUID = demo_id("ocr_document", OCR_DEMO_FILENAME)
OCR_DEMO_LINES = (
    "Nexora Facilities Notice",
    "The Pune office cafeteria will be closed on 14 November 2026.",
    "Contact the Facilities Desk on extension 4417 for assistance.",
    "Visitor parking remains open throughout the closure.",
)


def build_demo_notice_png() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    size, line_height, gap = 42, 96, 22
    font = ImageFont.load_default(size=size)
    image = Image.new("RGB", (1900, 70 + line_height * len(OCR_DEMO_LINES)), "white")
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(OCR_DEMO_LINES):
        x = 40
        for word in line.split():
            draw.text((x, 35 + row * line_height), word, fill="black", font=font)
            x += int(draw.textlength(word, font=font)) + gap
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=False)
    return buffer.getvalue()


async def seed_ocr_demo_document(session_factory, embedding_service=None, engine=None) -> bool:  # noqa: ANN001
    """Ingest the synthetic scanned notice through the real OCR pipeline. Idempotent.

    It is an all-staff notice, so every role gets an explicit document grant (access is still
    default deny for anything else). Returns True when it was created, False when it already
    existed. Raises the OCR errors if OCR is unavailable; nothing is faked.
    """
    from sqlalchemy import select

    from app import models
    from app.services.ocr.ingestion import ingest_image

    async with session_factory() as session:
        if await session.get(models.Document, OCR_DEMO_DOCUMENT_ID) is not None:
            return False
    await ingest_image(
        filename=OCR_DEMO_FILENAME,
        content_type="image/png",
        content=build_demo_notice_png(),
        session_factory=session_factory,
        owner_user_id=None,
        embedding_service=embedding_service,
        engine=engine,
        document_id=OCR_DEMO_DOCUMENT_ID,
    )
    async with session_factory() as session:
        document = await session.get(models.Document, OCR_DEMO_DOCUMENT_ID)
        document.classification = "INTERNAL"
        role_ids = list(await session.scalars(select(models.Role.id)))
        session.add_all(
            models.DocumentRoleAccess(document_id=OCR_DEMO_DOCUMENT_ID, role_id=role_id) for role_id in role_ids
        )
        await session.commit()
    return True
