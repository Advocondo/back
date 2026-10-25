"""add landing page blocks and images

Revision ID: 183ab32038c5
Revises: 79f61dbc2fd4
Create Date: 2026-10-22 03:19:59.296119

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "183ab32038c5"
down_revision: str | Sequence[str] | None = "79f61dbc2fd4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The landing page content at the deploy, from the approved layout (ui-kit,
# ui_kits/site_institucional/Sections.jsx); from then on the Administrator edits it
# (US04). Frozen here on purpose: later changes to the texts go through the API.
# The prototype's reviews are paraphrased placeholders and are left out, since only
# real reviews may be published; the WhatsApp number and the social media links are
# not in the prototype either.
INITIAL_CONTENT: dict[str, dict[str, Any]] = {
    "hero": {
        "title": "Seu direito é a nossa luta!",
        "subtitle": (
            "Há mais de 14 anos defendendo os seus direitos com ética e "
            "responsabilidade, oferecendo soluções jurídicas altamente "
            "eficazes."
        ),
        "button_label": "Fale conosco no WhatsApp",
    },
    "practice_areas": {
        "title": "Se você está enfrentando problemas de:",
        "areas": [
            {
                "title": "Direito Condominial",
                "description": (
                    "Somos especialistas em Direito Condominial! Temos mais de 14 "
                    "anos de experiência!"
                ),
            },
            {
                "title": "Direito Imobiliário",
                "description": (
                    "Problemas com questões relacionadas a imóveis, incluindo compra,"
                    " venda, locação, condomínios e litígios imobiliários?"
                ),
            },
            {
                "title": "Direito Civil",
                "description": (
                    "Estamos aqui para resolver questões relacionadas a contratos, "
                    "responsabilidade civil, disputas de propriedade, entre outros."
                ),
            },
            {
                "title": "Direito do Consumidor",
                "description": (
                    "Deixe-nos ajudar em questões como problemas com produtos ou "
                    "serviços defeituosos, cobranças indevidas, entre outros."
                ),
            },
            {
                "title": "Família e Sucessões",
                "description": (
                    "Estamos aqui para resolver ou cuidar de divórcio, guarda e "
                    "visitação dos filhos, partilha de bens, testamentos, "
                    "inventários, pensão alimentícia e outros."
                ),
            },
            {
                "title": "Outras áreas do Direito",
                "description": (
                    "Não hesite em nos contatar para obter aconselhamento jurídico "
                    "confiável e excelente em qualquer área do Direito."
                ),
            },
        ],
        "closing_text": (
            "Chegou a hora de assumirmos o seu caso para fazer valer os seus direitos!"
        ),
    },
    "online_service": {
        "title": "Também atendemos online para todo o Brasil.",
        "text": (
            "Nosso escritório de advocacia realiza atendimentos virtuais para"
            " clientes em outros estados. Se este é o seu caso, saiba que "
            "pode contar conosco."
        ),
        "button_label": "Quero ser atendido por um especialista",
    },
    "condominium_advisory": {
        "title": "Assessoria jurídica para condomínios",
        "paragraphs": [
            (
                "Um condomínio bem assessorado, juridicamente, corre menos riscos"
                " de enfrentar problemas em seus contratos com prestadores de "
                "serviços, condôminos e até mesmo com a própria construtora do "
                "edifício."
            ),
            (
                "Temos uma vasta experiência no assessoramento de síndicos para "
                "melhorarem a gestão de seus condomínios, dando foco total na "
                "recuperação de crédito, diminuindo, significativamente, dívidas "
                "condominiais."
            ),
            (
                "Dispomos de profissionais com conhecimento irrestrito da área e "
                "suporte técnico para atender as demandas de nossos clientes de "
                "forma personalizada."
            ),
            (
                "Nosso maior objetivo é agir preventivamente, em todas as "
                "situações, para resguardar os direitos dos nossos clientes e "
                "evitar danos para eles."
            ),
        ],
    },
    "reviews": {
        "title": "Veja o que nossos clientes falam sobre nós:",
        "reviews": [],
        "call_to_review_title": "Nos avalie no Google também",
        "call_to_review_text": (
            "Sua avaliação é importante para que outras pessoas que precisam "
            "de profissionais sérios nos encontrem."
        ),
        "button_label": "Avaliar",
        "google_reviews_url": None,
    },
    "why_us": {
        "title": "Ainda tem dúvidas se devemos assumir o seu caso?",
        "paragraphs": [
            ("Nosso diferencial é a prestação de um atendimento personalizado."),
            (
                "Esse conceito, onde a advocacia é vista como um trabalho "
                "artesanal, aumenta drasticamente as chances de êxito nas causas "
                "que assumimos, pois conseguimos atender cirurgicamente as "
                "necessidades de cada cliente, prestando uma assessoria jurídica "
                "altamente eficaz."
            ),
            (
                "Nosso maior objetivo é resguardar nossos clientes de todo e "
                "qualquer prejuízo financeiro, físico e moral."
            ),
            (
                "Com muita ética e competência, ao longo de mais de 14 anos de "
                "experiência no mundo jurídico, temos o prazer de carregar em "
                "nosso histórico mais de 95% de causas ganhas na justiça."
            ),
        ],
        "button_label": "Quero ser atendido por um especialista",
    },
    "team": {
        "title": "Conheça nossa equipe",
        "members": [
            {
                "name": "Dr. Edson Alexandre",
                "role": "Advogado Sócio",
                "photo_id": None,
            },
            {
                "name": "Dra. Amanda Pessoa",
                "role": "Advogada Sócia",
                "photo_id": None,
            },
            {
                "name": "Emanoela Felício",
                "role": "Recuperação de crédito",
                "photo_id": None,
            },
            {
                "name": "Dra. Sarah Holanda",
                "role": "Advogada",
                "photo_id": None,
            },
            {
                "name": "Dr. Leonor Soares",
                "role": "Advogado",
                "photo_id": None,
            },
            {
                "name": "Dr. Paulo Roberto",
                "role": "Advogado",
                "photo_id": None,
            },
        ],
        "highlights": [
            "Atendimento Personalizado.",
            "Profissionalismo e Dedicação.",
            "Equipe altamente experiente e preparada.",
        ],
    },
    "contact_form": {
        "title": "Preencha o formulário abaixo com as informações solicitadas",
        "subtitle": "Nossa equipe entrará em contato o mais breve possível!",
    },
    "visit": {
        "title": "Venha nos fazer uma visita",
        "text": "Teremos o prazer em te receber para tomarmos um café!",
        "button_label": "Fale conosco no WhatsApp",
    },
    "contact": {
        "phone": "6130218539",
        "whatsapp": None,
        "email": "edson.alexandre.adv@gmail.com",
        "address": (
            "Rua Copaíba, Lote 1, Torre B, Sala 1910 — DF Century Plaza, "
            "Águas Claras/DF"
        ),
        "opening_hours": "Segunda a sexta de 09h às 17h",
        "facebook_url": None,
        "instagram_url": None,
    },
}


def upgrade() -> None:
    landing_blocks = op.create_table(
        "landing_blocks",
        sa.Column("key", sa.String(length=30), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "key IN ('hero', 'practice_areas', 'online_service', "
            "'condominium_advisory', 'reviews', 'why_us', 'team', 'contact_form', "
            "'visit', 'contact')",
            name=op.f("ck_landing_blocks_landing_block_key"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_landing_blocks")),
        sa.UniqueConstraint("key", name=op.f("uq_landing_blocks_key")),
    )
    op.create_table(
        "landing_images",
        sa.Column("media_type", sa.String(length=30), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "media_type IN ('image/png', 'image/jpeg', 'image/webp')",
            name=op.f("ck_landing_images_image_media_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_landing_images")),
    )
    op.bulk_insert(
        landing_blocks,
        [{"key": key, "content": content} for key, content in INITIAL_CONTENT.items()],
    )


def downgrade() -> None:
    op.drop_table("landing_images")
    op.drop_table("landing_blocks")
