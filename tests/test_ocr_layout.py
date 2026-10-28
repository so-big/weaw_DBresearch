from dbresearch.ocr_layout import Word, build_lines, join_words, page_text

H = 40  # text height in pixels


def word(text: str, left: int, width: int = 30, conf: float = 90.0, top: int = 100) -> Word:
    return Word(text, left, top, width, H, conf)


def test_thai_clusters_with_narrow_gaps_are_joined():
    # gaps of 0.1·H between clusters → one word
    words = [word("สั", 0), word("ญ", 34), word("ญา", 68)]
    assert join_words(words) == "สัญญา"


def test_wide_gap_between_thai_words_keeps_a_space():
    words = [word("ขาออก", 0, 100), word("คณะ", 100 + int(0.8 * H))]
    assert join_words(words) == "ขาออก คณะ"


def test_latin_words_keep_normal_spaces():
    words = [word("Future", 0, 120), word("Proofing", 120 + int(0.3 * H), 160)]
    assert join_words(words) == "Future Proofing"


def test_period_hugging_thai_is_joined():
    words = [word("พ", 0, 30), word(".", 31, 6), word("ศ", 38, 30), word(".", 69, 6)]
    assert join_words(words) == "พ.ศ."


def test_words_are_ordered_by_position_not_input_order():
    words = [word("ญา", 68), word("สั", 0), word("ญ", 34)]
    assert join_words(words) == "สัญญา"


def _tesseract_dict(rows):
    keys = ("text", "conf", "left", "top", "width", "height", "block_num", "par_num", "line_num")
    return {k: [r[i] for r in rows] for i, k in enumerate(keys)}


def test_build_lines_groups_sorts_normalises_and_filters_noise():
    data = _tesseract_dict(
        [
            # second line on the page, given first
            ("หน", 95, 0, 200, 30, H, 1, 1, 2),
            ("้า", 95, 32, 200, 30, H, 1, 1, 2),
            ("สั", 92, 0, 100, 30, H, 1, 1, 1),
            ("ญญา", 92, 33, 100, 60, H, 1, 1, 1),
            ("", -1, 0, 0, 0, 0, 1, 1, 1),  # Tesseract's empty structural rows
            ("ee", 20, 0, 300, 20, H, 2, 1, 1),  # watermark noise, low confidence
        ]
    )
    lines = build_lines(data)
    assert [line.text for line in lines] == ["สัญญา", "หน้า", "ee"]
    assert page_text(lines) == "สัญญา\nหน้า"
