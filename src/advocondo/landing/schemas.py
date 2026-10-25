import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    UrlConstraints,
    model_validator,
)

from advocondo.common.normalization import keep_only_digits

MAX_TITLE_LENGTH = 150
MAX_TEXT_LENGTH = 1000
MAX_EMAIL_LENGTH = 254
MIN_REVIEW_RATING = 1
MAX_REVIEW_RATING = 5
MAX_PRACTICE_AREAS = 12
MAX_PARAGRAPHS = 6
MAX_REVIEWS = 8
MAX_TEAM_MEMBERS = 12
MAX_TEAM_HIGHLIGHTS = 6

Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_LENGTH),
]
Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH),
]
Phone = Annotated[
    str, BeforeValidator(keep_only_digits), StringConstraints(pattern=r"^\d{10,11}$")
]
# Plain http links would be blocked as mixed content on the https site.
HttpsUrl = Annotated[HttpUrl, UrlConstraints(allowed_schemes=["https"])]


class BlockContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def image_ids(self) -> set[uuid.UUID]:
        return set()


class HeroContent(BlockContent):
    title: Title
    subtitle: Text
    button_label: Title


class PracticeArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    description: Text


class PracticeAreasContent(BlockContent):
    title: Title
    areas: list[PracticeArea] = Field(min_length=1, max_length=MAX_PRACTICE_AREAS)
    closing_text: Text


class OnlineServiceContent(BlockContent):
    title: Title
    text: Text
    button_label: Title


class CondominiumAdvisoryContent(BlockContent):
    title: Title
    paragraphs: list[Text] = Field(min_length=1, max_length=MAX_PARAGRAPHS)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: Title
    # What Google shows under the name, such as "Local Guide" or "2 comentários".
    author_details: Title | None = None
    rating: int = Field(ge=MIN_REVIEW_RATING, le=MAX_REVIEW_RATING)
    text: Text


class ReviewsContent(BlockContent):
    title: Title
    # Copied by hand from Google: there is no integration with the Google API.
    reviews: list[Review] = Field(max_length=MAX_REVIEWS)
    call_to_review_title: Title
    call_to_review_text: Text
    button_label: Title
    google_reviews_url: HttpsUrl | None = None


class WhyUsContent(BlockContent):
    title: Title
    paragraphs: list[Text] = Field(min_length=1, max_length=MAX_PARAGRAPHS)
    button_label: Title


class TeamMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Title
    role: Title
    # Uploaded first through POST /landing/images; without it the site shows a placeholder.
    photo_id: uuid.UUID | None = None


class TeamContent(BlockContent):
    title: Title
    members: list[TeamMember] = Field(min_length=1, max_length=MAX_TEAM_MEMBERS)
    highlights: list[Title] = Field(max_length=MAX_TEAM_HIGHLIGHTS)

    def image_ids(self) -> set[uuid.UUID]:
        return {member.photo_id for member in self.members if member.photo_id}


class ContactFormContent(BlockContent):
    title: Title
    subtitle: Text


class VisitContent(BlockContent):
    title: Title
    text: Text
    button_label: Title


class ContactContent(BlockContent):
    """Shown in the footer and used by every WhatsApp and social media link."""

    phone: Phone | None = None
    whatsapp: Phone | None = None
    email: EmailStr | None = Field(default=None, max_length=MAX_EMAIL_LENGTH)
    address: Text | None = None
    opening_hours: Title | None = None
    facebook_url: HttpsUrl | None = None
    instagram_url: HttpsUrl | None = None


class LandingContent(BaseModel):
    """Every section of the landing page; each field name is a `LandingBlockKey`."""

    hero: HeroContent
    practice_areas: PracticeAreasContent
    online_service: OnlineServiceContent
    condominium_advisory: CondominiumAdvisoryContent
    reviews: ReviewsContent
    why_us: WhyUsContent
    team: TeamContent
    contact_form: ContactFormContent
    visit: VisitContent
    contact: ContactContent

    def blocks(self) -> dict[str, BlockContent]:
        return {name: getattr(self, name) for name in type(self).model_fields}

    def image_ids(self) -> set[uuid.UUID]:
        return set().union(*(block.image_ids() for block in self.blocks().values()))


class LandingUpdateRequest(BaseModel):
    """Only the sections sent are replaced, each one as a whole."""

    model_config = ConfigDict(extra="forbid")

    hero: HeroContent | None = None
    practice_areas: PracticeAreasContent | None = None
    online_service: OnlineServiceContent | None = None
    condominium_advisory: CondominiumAdvisoryContent | None = None
    reviews: ReviewsContent | None = None
    why_us: WhyUsContent | None = None
    team: TeamContent | None = None
    contact_form: ContactFormContent | None = None
    visit: VisitContent | None = None
    contact: ContactContent | None = None

    @model_validator(mode="after")
    def _has_a_section_to_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Informe ao menos uma seção para alterar.")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Uma seção não pode ser removida da página.")
        return self

    def changed_blocks(self) -> dict[str, BlockContent]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class LandingImageResponse(BaseModel):
    id: uuid.UUID
