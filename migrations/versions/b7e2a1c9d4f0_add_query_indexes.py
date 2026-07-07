"""Sık sorgulanan sütunlar için indeksler."""

from alembic import op

revision = "b7e2a1c9d4f0"
down_revision = "48d3305d9f74"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_kaynak_ilan_durumu", "kaynak", ["ilan_durumu"], unique=False)
    op.create_index("ix_kaynak_user_id", "kaynak", ["user_id"], unique=False)
    op.create_index("ix_atik_ilan_durumu", "atik", ["ilan_durumu"], unique=False)
    op.create_index("ix_atik_user_id", "atik", ["user_id"], unique=False)
    op.create_index("ix_mesaj_receiver_okundu", "mesaj", ["receiver_id", "is_read"], unique=False)
    op.create_index("ix_comment_kaynak_parent", "comment", ["kaynak_id", "parent_id"], unique=False)
    op.create_index("ix_comment_atik_parent", "comment", ["atik_id", "parent_id"], unique=False)
    op.create_index("ix_favori_user_id", "favori", ["user_id"], unique=False)
    op.create_index("ix_bildirim_user_okundu", "bildirim", ["user_id", "okundu"], unique=False)
    op.create_index("ix_goruntulenme_kaynak_id", "goruntulenme", ["kaynak_id"], unique=False)
    op.create_index("ix_goruntulenme_atik_id", "goruntulenme", ["atik_id"], unique=False)


def downgrade():
    op.drop_index("ix_goruntulenme_atik_id", table_name="goruntulenme")
    op.drop_index("ix_goruntulenme_kaynak_id", table_name="goruntulenme")
    op.drop_index("ix_bildirim_user_okundu", table_name="bildirim")
    op.drop_index("ix_favori_user_id", table_name="favori")
    op.drop_index("ix_comment_atik_parent", table_name="comment")
    op.drop_index("ix_comment_kaynak_parent", table_name="comment")
    op.drop_index("ix_mesaj_receiver_okundu", table_name="mesaj")
    op.drop_index("ix_atik_user_id", table_name="atik")
    op.drop_index("ix_atik_ilan_durumu", table_name="atik")
    op.drop_index("ix_kaynak_user_id", table_name="kaynak")
    op.drop_index("ix_kaynak_ilan_durumu", table_name="kaynak")
