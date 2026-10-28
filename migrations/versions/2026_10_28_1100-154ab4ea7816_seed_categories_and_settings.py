"""Seed category groups/options (DESIGN §6) and share-link settings.

Reference data only; ADMIN edits it afterwards in the app. The options come from the real
proposal form (เอกสารแนบหมายเลข 5) and the mock; aliases are heading/label variants seen on forms.

Downgrade deletes the seeded rows. It fails if documents already use these categories,
which is intended: those links must not be dropped silently.

Revision ID: 154ab4ea7816
Revises: 0e8747de3308
Create Date: 2026-10-28 11:00:34.844576
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "154ab4ea7816"
down_revision: str | Sequence[str] | None = "0e8747de3308"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# key: (name_th, name_en, heading aliases, multi, [(option_th, option aliases), ...])
GROUPS: dict[str, tuple[str, str, list[str], bool, list[tuple[str, list[str]]]]] = {
    "agency": (
        "แหล่งทุน",
        "Funding agency",
        [],
        False,
        [
            (
                "สำนักงานปลัดกระทรวงการอุดมศึกษา วิทยาศาสตร์ วิจัยและนวัตกรรม",
                ["สป.อว.", "สปอว"],
            ),
            ("งบประมาณรายได้คณะวิศวกรรมศาสตร์", ["รายได้คณะ", "งบประมาณรายได้คณะ"]),
        ],
    ),
    "grant_programme": (
        "โครงการทุน",
        "Grant programme",
        [],
        False,
        [("วิจัยสถาบัน", [])],
    ),
    "research_type": (
        "ประเภทการวิจัย",
        "Research type",
        ["ประเภทวิจัย"],
        False,
        [
            ("เพื่อแก้ปัญหา", []),
            ("เพื่อการวางแผนพัฒนา", []),
            ("เพื่อการประกันคุณภาพ", []),
            ("พื้นฐาน", []),
            ("ทดลองและพัฒนา", []),
        ],
    ),
    "research_group": (
        "กลุ่มการวิจัย",
        "Research group",
        [],
        False,
        [
            ("นิสิต / นักศึกษา", ["นิสิต/นักศึกษา"]),
            ("บุคลากร", []),
            ("หลักสูตร / โปรแกรมการศึกษา", ["หลักสูตร/โปรแกรมการศึกษา"]),
            ("การเงิน / งบประมาณ", ["การเงิน/งบประมาณ"]),
            ("อาคารสถานที่ และสิ่งอำนวยความสะดวก", []),
            ("วิทยาศาสตร์เทคโนโลยี", []),
            ("วิทยาศาสตร์สุขภาพ", []),
        ],
    ),
    "grant_type": (
        "ประเภททุน",
        "Grant type",
        [],
        False,
        [
            ("นักวิจัยรุ่นใหม่", []),
            ("ทุนวิจัยสำหรับนักวิจัยที่มีประสบการณ์ด้านการวิจัย", []),
        ],
    ),
    "discipline": (
        "สาขาวิชาการ",
        "Discipline",
        [],
        False,
        [("วิศวกรรมศาสตร์และอุตสาหกรรมวิจัย", []), ("นิติศาสตร์", [])],
    ),
}

# Share-link limits (DESIGN §1): default 24 h, USER max 7 days, ADMIN max 30 days.
SETTINGS = {
    "share.default_ttl_hours": 24,
    "share.max_ttl_user_hours": 7 * 24,
    "share.max_ttl_admin_hours": 30 * 24,
    "share.max_failed_attempts": 10,
}


def upgrade() -> None:
    conn = op.get_bind()
    for sort, (key, (name_th, name_en, aliases, multi, options)) in enumerate(GROUPS.items()):
        group_id = conn.execute(
            sa.text(
                "INSERT INTO category_groups (key, name_th, name_en, aliases, multi, sort) "
                "VALUES (:key, :name_th, :name_en, :aliases, :multi, :sort) RETURNING id"
            ),
            {
                "key": key,
                "name_th": name_th,
                "name_en": name_en,
                "aliases": aliases,
                "multi": multi,
                "sort": sort,
            },
        ).scalar_one()
        for option_sort, (option, option_aliases) in enumerate(options):
            conn.execute(
                sa.text(
                    "INSERT INTO categories (group_id, name_th, aliases, sort) "
                    "VALUES (:group_id, :name_th, :aliases, :sort)"
                ),
                {
                    "group_id": group_id,
                    "name_th": option,
                    "aliases": option_aliases,
                    "sort": option_sort,
                },
            )
    for key, value in SETTINGS.items():
        conn.execute(
            sa.text("INSERT INTO settings (key, value) VALUES (:key, CAST(:value AS jsonb))"),
            {"key": key, "value": json.dumps(value)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM settings WHERE key = ANY(:keys)"), {"keys": list(SETTINGS)})
    conn.execute(
        sa.text(
            "DELETE FROM categories WHERE group_id IN "
            "(SELECT id FROM category_groups WHERE key = ANY(:keys))"
        ),
        {"keys": list(GROUPS)},
    )
    conn.execute(
        sa.text("DELETE FROM category_groups WHERE key = ANY(:keys)"), {"keys": list(GROUPS)}
    )
