import pytest

from dbresearch.textnorm import normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ช ื่อโครงการ", "ชื่อโครงการ"),  # space before a combining vowel
        ("หน ้า 1", "หน้า 1"),  # space before a tone mark
        ("สัญญาเลขที่​ R2568E001", "สัญญาเลขที่ R2568E001"),  # zero-width space
        ("พ.ศ. ๒๕๖๘", "พ.ศ. 2568"),  # Thai digits
        ("ประจําปี", "ประจำปี"),  # decomposed SARA AM
        ("  งบประมาณรวม \t  10,000  ", "งบประมาณรวม 10,000"),
        ("line one\n\n   \nline two", "line one\nline two"),
    ],
)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_keeps_spaces_between_thai_words():
    assert normalize("สัญญารับทุน อุดหนุนการวิจัย") == "สัญญารับทุน อุดหนุนการวิจัย"
