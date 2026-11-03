from __future__ import annotations

import asyncio
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.core.config import get_settings
from app.services.presentation import image_resources
from app.services.presentation.contracts import FreeformDeckBlueprint
from app.services.presentation.image_filler import ImageFiller
from app.services.presentation.image_native.image_page_builder import ImagePageBuilder
from app.services.presentation.pptx_compiler import PptxCompiler
from app.utils import oss_uploader


@pytest.fixture
def storage(monkeypatch, tmp_path):
    settings = get_settings().model_copy(update={
        "STORAGE_BACKEND": "local", "LOCAL_STORAGE_PATH": str(tmp_path),
        "FILE_PUBLIC_PATH_PREFIX": "/askai-api/api/files", "END_USER_AUTH_SECRET": "test-secret",
    })
    monkeypatch.setattr(oss_uploader, "get_settings", lambda: settings)
    monkeypatch.setattr(image_resources, "get_settings", lambda: settings)
    uploader = oss_uploader.AliyunOSSUploader()
    data = BytesIO()
    Image.new("RGB", (1600, 900), "blue").save(data, format="PNG")
    uploader.write_bytes("user-a/slide.png", data.getvalue())
    return uploader


def deck(reference: str) -> FreeformDeckBlueprint:
    return FreeformDeckBlueprint(deck_id="delivery", pages=[
        ImagePageBuilder().build(page_plan={"page_id": f"page-{index}"}, source_slide_image_url=reference)
        for index in (1, 2)
    ])


def test_local_slide_images_are_embedded_in_every_pptx_page(storage):
    payload = PptxCompiler().compile(deck(storage.sign_url("user-a/slide.png")), user_id="user-a")
    with ZipFile(BytesIO(payload)) as archive:
        assert any(name.startswith("ppt/media/") for name in archive.namelist())
        assert b"/api/files/" not in archive.read("ppt/slides/slide1.xml")
    result = Presentation(BytesIO(payload))
    assert len(result.slides) == 2
    assert all(any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in slide.shapes)
               for slide in result.slides)


def test_stored_images_do_not_trigger_more_generation(storage, monkeypatch):
    async def forbidden(**kwargs):
        raise AssertionError("Existing images must never be regenerated")
    from app.services.presentation import image_filler
    monkeypatch.setattr(image_filler, "generate_infographic_asset", forbidden)
    blueprint = deck(storage.sign_url("user-a/slide.png"))
    assert asyncio.run(ImageFiller().fill(blueprint, user_id="user-a")) is blueprint


def test_image_read_failure_rejects_export_instead_of_using_placeholder(storage):
    with pytest.raises(FileNotFoundError):
        PptxCompiler().compile(deck(storage.sign_url("user-a/missing.png")), user_id="user-a")
    storage.write_bytes("user-a/broken.png", b"invalid-image")
    with pytest.raises(Exception, match="cannot identify image"):
        PptxCompiler().compile(deck(storage.sign_url("user-a/broken.png")), user_id="user-a")


def test_export_rejects_cross_user_and_traversal_references(storage):
    with pytest.raises(ValueError, match="does not belong"):
        PptxCompiler().compile(deck(storage.sign_url("user-a/slide.png")), user_id="user-b")
    with pytest.raises(ValueError, match="Invalid slide image"):
        image_resources.read_stored_image("/api/files/user-b/../user-a/slide.png", user_id="user-b")


def test_owned_export_survives_expired_download_links(storage):
    # An expired/unsigned link is not a download capability, but the owner can
    # still export an old deck using the persisted resource identity.
    url = "/api/files/user-a/slide.png?expires=1&signature=invalid"
    with pytest.raises(ValueError, match="signature"):
        image_resources.read_stored_image(url)
    assert image_resources.read_stored_image(url, user_id="user-a")


def test_http_failure_and_empty_native_page_never_export_as_success(monkeypatch):
    monkeypatch.setattr(PptxCompiler, "_download_image", staticmethod(lambda _: None))
    with pytest.raises(ValueError, match="could not be loaded"):
        PptxCompiler().compile(deck("https://example.test/missing.png"))
    blueprint = deck("https://example.test/slide.png")
    blueprint.pages[0].blocks = []
    with pytest.raises(ValueError, match="no embedded visual"):
        PptxCompiler().compile(blueprint)


def test_local_preview_storage_and_real_export_chain(storage):
    from types import SimpleNamespace
    from app.services.documents import document_service
    from app.services.presentation.contracts import StoryDeckPlan
    from app.services.presentation.image_native.pipeline import ImageNativePresentationPipeline

    async def scenario():
        pipeline = ImageNativePresentationPipeline()

        async def story(**kwargs):
            return StoryDeckPlan(deck_id="delivery", deck_goal="Two slide introduction", target_audience="Business users", pages=[])

        async def pages(**kwargs):
            return deck(storage.sign_url("user-a/slide.png"))

        pipeline._story_planner = SimpleNamespace(build=story)
        pipeline._page_planner = SimpleNamespace(build=pages)
        result = await pipeline.build(messages=[], output_spec={"user_id": "user-a", "language": "en"})
        bundle = result["preview_bundle"]
        assert bundle.slide_count == 2
        assert b"/askai-api/api/files/" in storage.read_bytes(bundle.html_preview.object_path)
        exported = await document_service.render_presentation_pptx(
            user_id="user-a", blueprint_object_path=bundle.deck_ir_artifact.object_path,
        )
        output = Presentation(BytesIO(storage.read_bytes(exported["object_path"])))
        assert len(output.slides) == 2
        assert all(any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in slide.shapes)
                   for slide in output.slides)

    asyncio.run(scenario())
