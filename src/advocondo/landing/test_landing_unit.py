import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from advocondo.landing.images import (
    JPEG_SIGNATURE,
    PNG_SIGNATURE,
    detect_media_type,
)
from advocondo.landing.models import ImageMediaType, LandingBlockKey
from advocondo.landing.schemas import (
    MAX_TEAM_MEMBERS,
    ContactContent,
    LandingContent,
    LandingUpdateRequest,
    ReviewsContent,
    TeamContent,
    TeamMember,
)
from tests.fixtures.landing import LANDING_CONTENT

WEBP_HEADER = b"RIFF\x24\x00\x00\x00WEBPVP8 "
PHOTO_ID = uuid.UUID("6f1c2a52-8d0b-4f7e-9d43-2b8f6c1e0a11")


def team_with(**overrides: Any) -> dict[str, Any]:
    return LANDING_CONTENT.team.model_dump(mode="json") | overrides


def reviews_with(**overrides: Any) -> dict[str, Any]:
    return LANDING_CONTENT.reviews.model_dump(mode="json") | overrides


class TestDetectMediaType:
    @pytest.mark.parametrize(
        ("data", "media_type"),
        [
            pytest.param(PNG_SIGNATURE + b"rest", ImageMediaType.PNG, id="png"),
            pytest.param(JPEG_SIGNATURE + b"rest", ImageMediaType.JPEG, id="jpeg"),
            pytest.param(WEBP_HEADER, ImageMediaType.WEBP, id="webp"),
        ],
    )
    def test_media_type_comes_from_the_file_signature(
        self, data: bytes, media_type: ImageMediaType
    ) -> None:
        assert detect_media_type(data) == media_type

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(b'<svg xmlns="http://www.w3.org/2000/svg"/>', id="svg"),
            pytest.param(b"GIF89a", id="gif"),
            pytest.param(b"RIFF\x24\x00\x00\x00WAVEfmt ", id="riff-that-is-not-webp"),
            pytest.param(b"", id="empty"),
        ],
    )
    def test_other_files_are_not_recognized(self, data: bytes) -> None:
        assert detect_media_type(data) is None


class TestLandingContent:
    def test_each_section_is_a_block_key(self) -> None:
        assert set(LandingContent.model_fields) == set(LandingBlockKey)

    def test_image_ids_are_the_team_photos(self) -> None:
        team = TeamContent.model_validate(
            team_with(
                members=[
                    {"name": "Dr. Edson Alexandre", "role": "Advogado Sócio"},
                    {
                        "name": "Dra. Amanda Pessoa",
                        "role": "Advogada",
                        "photo_id": PHOTO_ID,
                    },
                ]
            )
        )
        content = LANDING_CONTENT.model_copy(update={"team": team})

        assert content.image_ids() == {PHOTO_ID}


class TestBlockContent:
    def test_contact_phones_are_stored_as_digits(self) -> None:
        contact = ContactContent(phone="(61) 3021-8539", whatsapp="(61) 91234-5678")

        assert contact.phone == "6130218539"
        assert contact.whatsapp == "61912345678"

    def test_texts_are_trimmed(self) -> None:
        member = TeamMember(name="  Dr. Paulo Roberto ", role=" Advogado ")

        assert member.name == "Dr. Paulo Roberto"
        assert member.role == "Advogado"

    @pytest.mark.parametrize(
        ("schema", "fields"),
        [
            pytest.param(TeamContent, team_with(members=[]), id="team-without-members"),
            pytest.param(
                TeamContent,
                team_with(
                    members=[{"name": "Dr. X", "role": "Advogado"}]
                    * (MAX_TEAM_MEMBERS + 1)
                ),
                id="too-many-members",
            ),
            pytest.param(TeamContent, team_with(title="   "), id="blank-title"),
            pytest.param(TeamContent, team_with(slogan="Equipe"), id="unknown-field"),
            pytest.param(
                ReviewsContent,
                reviews_with(
                    reviews=[
                        {"author": "Bárbara Sampaio", "rating": 6, "text": "Ótimo."}
                    ]
                ),
                id="rating-above-five",
            ),
            pytest.param(
                ReviewsContent,
                reviews_with(google_reviews_url="http://g.page/r/escritorio"),
                id="link-without-https",
            ),
            pytest.param(
                ContactContent, {"phone": "3021-8539"}, id="phone-without-area-code"
            ),
            pytest.param(ContactContent, {"email": "contato@"}, id="invalid-email"),
        ],
    )
    def test_invalid_content_is_refused(
        self,
        schema: type[TeamContent | ReviewsContent | ContactContent],
        fields: dict[str, Any],
    ) -> None:
        with pytest.raises(ValidationError):
            schema.model_validate(fields)


class TestLandingUpdateRequest:
    def test_only_the_sections_sent_are_changed(self) -> None:
        request = LandingUpdateRequest.model_validate(
            {"contact": {"phone": "(61) 3021-8539"}}
        )

        assert list(request.changed_blocks()) == ["contact"]

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({}, id="no-section"),
            pytest.param({"hero": None}, id="section-sent-as-null"),
            pytest.param({"footer": {"text": "Rodapé"}}, id="unknown-section"),
        ],
    )
    def test_request_without_a_section_to_save_is_refused(
        self, fields: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError):
            LandingUpdateRequest.model_validate(fields)
