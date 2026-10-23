import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from advocondo.config import Settings
from advocondo.landing.images import PNG_SIGNATURE
from advocondo.landing.service import BYTES_PER_KILOBYTE
from advocondo.users.models import Role
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.landing import LANDING_CONTENT
from tests.fixtures.users import CreateUser

PNG_IMAGE = PNG_SIGNATURE + b"team member photo"
NEW_HERO = {
    "title": "Seu condomínio em boas mãos",
    "subtitle": "Recuperação de crédito condominial há mais de 14 anos.",
    "button_label": "Fale conosco no WhatsApp",
}
UNKNOWN_IMAGE_ID = uuid.UUID("0b7e9a3c-5d21-4f68-a0c4-7e2d9b1f3a55")
pytestmark = pytest.mark.usefixtures("landing_page")

NON_ADMIN_ROLES = [
    pytest.param(Role.OPERATOR, id="operator"),
    pytest.param(Role.CLIENT, id="client"),
]


@pytest.fixture
def admin_headers(
    create_user: CreateUser, authenticate_as: AuthenticateAs
) -> dict[str, str]:
    return authenticate_as(create_user(email="admin@example.com", role=Role.ADMIN))


def team_with_photos(*photo_ids: str | None) -> dict[str, Any]:
    team = LANDING_CONTENT.team.model_dump(mode="json")
    team["members"] = [
        {"name": f"Membro {number}", "role": "Advogado", "photo_id": photo_id}
        for number, photo_id in enumerate(photo_ids, start=1)
    ]
    return team


def update(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.patch("/landing", json=payload, headers=headers)
    return response


def upload(
    client: TestClient, headers: dict[str, str], content: bytes = PNG_IMAGE
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/landing/images",
        files={"file": ("foto.png", content, "image/png")},
        headers=headers,
    )
    return response


def upload_photo(client: TestClient, headers: dict[str, str]) -> str:
    image_id: str = upload(client, headers).json()["id"]
    return image_id


class TestGetLanding:
    def test_visitor_sees_every_section_without_logging_in(
        self, db_client: TestClient
    ) -> None:
        response = db_client.get("/landing")

        assert response.status_code == 200
        assert response.json() == LANDING_CONTENT.model_dump(mode="json")


class TestUpdateLanding:
    def test_change_is_public_after_saving(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """US04-CA01"""
        update(db_client, admin_headers, {"hero": NEW_HERO})

        response = db_client.get("/landing")

        assert response.json()["hero"] == NEW_HERO

    def test_response_is_the_whole_page_after_the_change(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = update(db_client, admin_headers, {"hero": NEW_HERO})

        assert response.status_code == 200
        assert response.json() == db_client.get("/landing").json()

    def test_sections_not_sent_keep_their_content(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        update(db_client, admin_headers, {"hero": NEW_HERO})

        update(db_client, admin_headers, {"contact": {"phone": "(61) 3021-8539"}})

        body = db_client.get("/landing").json()
        assert body["hero"] == NEW_HERO
        assert body["visit"] == LANDING_CONTENT.visit.model_dump(mode="json")

    def test_saving_a_section_again_replaces_it(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        update(db_client, admin_headers, {"hero": NEW_HERO})
        second_hero = {**NEW_HERO, "title": "Seu direito é a nossa luta!"}

        update(db_client, admin_headers, {"hero": second_hero})

        assert db_client.get("/landing").json()["hero"] == second_hero

    def test_team_member_can_be_removed(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        update(db_client, admin_headers, {"team": team_with_photos(None, None)})

        response = db_client.get("/landing")

        assert len(response.json()["team"]["members"]) == 2

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_only_the_administrator_edits_the_page(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US04-CA02"""
        headers = authenticate_as(create_user(role=role))

        response = update(db_client, headers, {"hero": NEW_HERO})

        assert response.status_code == 403
        assert db_client.get("/landing").json()["hero"] != NEW_HERO

    def test_visitor_cannot_edit_the_page(self, db_client: TestClient) -> None:
        """US04-CA02"""
        response = update(db_client, {}, {"hero": NEW_HERO})

        assert response.status_code == 401

    def test_invalid_section_is_refused(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = update(db_client, admin_headers, {"hero": {**NEW_HERO, "title": ""}})

        assert response.status_code == 422

    def test_photo_that_was_not_uploaded_is_refused(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        payload = {"team": team_with_photos(str(UNKNOWN_IMAGE_ID))}

        response = update(db_client, admin_headers, payload)

        assert response.status_code == 422
        assert response.json()["detail"] == (
            "A página usa uma imagem que não foi enviada. Envie a imagem de novo."
        )

    def test_team_member_photo_is_shown_on_the_page(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """US04-CA01"""
        photo_id = upload_photo(db_client, admin_headers)

        update(db_client, admin_headers, {"team": team_with_photos(photo_id)})

        members = db_client.get("/landing").json()["team"]["members"]
        assert members[0]["photo_id"] == photo_id
        assert db_client.get(f"/landing/images/{photo_id}").content == PNG_IMAGE

    def test_replaced_photo_is_deleted(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        old_photo_id = upload_photo(db_client, admin_headers)
        update(db_client, admin_headers, {"team": team_with_photos(old_photo_id)})
        new_photo_id = upload_photo(db_client, admin_headers)

        update(db_client, admin_headers, {"team": team_with_photos(new_photo_id)})

        assert db_client.get(f"/landing/images/{old_photo_id}").status_code == 404
        assert db_client.get(f"/landing/images/{new_photo_id}").status_code == 200


class TestUploadImage:
    def test_administrator_uploads_an_image(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = upload(db_client, admin_headers)

        assert response.status_code == 201
        assert uuid.UUID(response.json()["id"])

    def test_image_is_served_with_its_type_and_cached(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        image_id = upload_photo(db_client, admin_headers)

        response = db_client.get(f"/landing/images/{image_id}")

        assert response.status_code == 200
        assert response.content == PNG_IMAGE
        assert response.headers["content-type"] == "image/png"
        assert "immutable" in response.headers["cache-control"]
        assert response.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_only_the_administrator_uploads_images(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US04-CA02"""
        response = upload(db_client, authenticate_as(create_user(role=role)))

        assert response.status_code == 403

    def test_visitor_cannot_upload_images(self, db_client: TestClient) -> None:
        """US04-CA02"""
        response = upload(db_client, {})

        assert response.status_code == 401

    def test_image_over_the_size_limit_is_refused(
        self,
        db_client: TestClient,
        admin_headers: dict[str, str],
        settings: Settings,
    ) -> None:
        max_bytes = settings.landing_image_max_kilobytes * BYTES_PER_KILOBYTE
        content = PNG_SIGNATURE + b"0" * (max_bytes - len(PNG_SIGNATURE) + 1)

        response = upload(db_client, admin_headers, content)

        assert response.status_code == 422
        assert response.json()["detail"] == (
            f"A imagem passa de {settings.landing_image_max_kilobytes} KB."
        )

    def test_image_at_the_size_limit_is_accepted(
        self,
        db_client: TestClient,
        admin_headers: dict[str, str],
        settings: Settings,
    ) -> None:
        max_bytes = settings.landing_image_max_kilobytes * BYTES_PER_KILOBYTE
        content = PNG_SIGNATURE + b"0" * (max_bytes - len(PNG_SIGNATURE))

        response = upload(db_client, admin_headers, content)

        assert response.status_code == 201

    def test_file_that_is_not_an_accepted_image_is_refused(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'

        response = upload(db_client, admin_headers, svg)

        assert response.status_code == 422
        assert response.json()["detail"] == "Envie uma imagem PNG, JPEG ou WebP."


class TestGetImage:
    def test_unknown_image_is_not_found(self, db_client: TestClient) -> None:
        response = db_client.get(f"/landing/images/{UNKNOWN_IMAGE_ID}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Imagem não encontrada."


class TestDeleteImage:
    def test_image_never_used_is_deleted(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        image_id = upload_photo(db_client, admin_headers)

        response = db_client.delete(
            f"/landing/images/{image_id}", headers=admin_headers
        )

        assert response.status_code == 204
        assert db_client.get(f"/landing/images/{image_id}").status_code == 404

    def test_image_in_use_is_kept(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        image_id = upload_photo(db_client, admin_headers)
        update(db_client, admin_headers, {"team": team_with_photos(image_id)})

        response = db_client.delete(
            f"/landing/images/{image_id}", headers=admin_headers
        )

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "A imagem está em uso na página institucional."
        )

    def test_unknown_image_is_not_found(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = db_client.delete(
            f"/landing/images/{UNKNOWN_IMAGE_ID}", headers=admin_headers
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_only_the_administrator_deletes_images(
        self,
        db_client: TestClient,
        admin_headers: dict[str, str],
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US04-CA02"""
        image_id = upload_photo(db_client, admin_headers)
        headers = authenticate_as(create_user(role=role))

        response = db_client.delete(f"/landing/images/{image_id}", headers=headers)

        assert response.status_code == 403
