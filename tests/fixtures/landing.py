import pytest
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from advocondo.landing.models import LandingBlock, LandingBlockKey
from advocondo.landing.schemas import (
    CondominiumAdvisoryContent,
    ContactContent,
    ContactFormContent,
    HeroContent,
    LandingContent,
    OnlineServiceContent,
    PracticeArea,
    PracticeAreasContent,
    Review,
    ReviewsContent,
    TeamContent,
    TeamMember,
    VisitContent,
    WhyUsContent,
)

# In production the migration writes the initial content; the test database is built
# from the models, so the tests write this page instead.
LANDING_CONTENT = LandingContent(
    hero=HeroContent(
        title="Seu direito é a nossa luta!",
        subtitle="Há mais de 14 anos defendendo os seus direitos.",
        button_label="Fale conosco no WhatsApp",
    ),
    practice_areas=PracticeAreasContent(
        title="Se você está enfrentando problemas de:",
        areas=[
            PracticeArea(
                title="Direito Condominial",
                description="Somos especialistas em Direito Condominial!",
            ),
        ],
        closing_text="Chegou a hora de assumirmos o seu caso!",
    ),
    online_service=OnlineServiceContent(
        title="Também atendemos online para todo o Brasil.",
        text="Atendemos clientes de outros estados.",
        button_label="Quero ser atendido por um especialista",
    ),
    condominium_advisory=CondominiumAdvisoryContent(
        title="Assessoria jurídica para condomínios",
        paragraphs=["Focamos na recuperação de crédito condominial."],
    ),
    reviews=ReviewsContent(
        title="Veja o que nossos clientes falam sobre nós:",
        reviews=[
            Review(
                author="Bárbara Sampaio",
                author_details="2 comentários",
                rating=5,
                text="Equipe atenciosa e dedicada.",
            ),
        ],
        call_to_review_title="Nos avalie no Google também",
        call_to_review_text="Sua avaliação ajuda outras pessoas a nos encontrar.",
        button_label="Avaliar",
        google_reviews_url=HttpUrl("https://g.page/r/escritorio/review"),
    ),
    why_us=WhyUsContent(
        title="Ainda tem dúvidas se devemos assumir o seu caso?",
        paragraphs=["Nosso diferencial é o atendimento personalizado."],
        button_label="Quero ser atendido por um especialista",
    ),
    team=TeamContent(
        title="Conheça nossa equipe",
        members=[
            TeamMember(name="Dr. Edson Alexandre", role="Advogado Sócio"),
            TeamMember(name="Dra. Amanda Pessoa", role="Advogada Sócia"),
        ],
        highlights=["Atendimento Personalizado."],
    ),
    contact_form=ContactFormContent(
        title="Preencha o formulário abaixo",
        subtitle="Nossa equipe entrará em contato o mais breve possível!",
    ),
    visit=VisitContent(
        title="Venha nos fazer uma visita",
        text="Teremos o prazer em te receber para tomarmos um café!",
        button_label="Fale conosco no WhatsApp",
    ),
    contact=ContactContent(
        phone="6130218539",
        whatsapp="61912345678",
        email="contato@example.com",
        address="Rua Copaíba, Lote 1, Águas Claras/DF",
        opening_hours="Segunda a sexta de 09h às 17h",
        facebook_url=HttpUrl("https://facebook.com/escritorio"),
        instagram_url=HttpUrl("https://instagram.com/escritorio"),
    ),
)


@pytest.fixture
def landing_page(db_session: Session) -> LandingContent:
    """Writes one row per section with `LANDING_CONTENT`, as the migration does."""
    for name, block in LANDING_CONTENT.blocks().items():
        db_session.add(
            LandingBlock(
                key=LandingBlockKey(name), content=block.model_dump(mode="json")
            )
        )
    db_session.flush()
    return LANDING_CONTENT
