import messages


def test_all_texts_are_safe():
    texts = messages.all_texts()
    assert len(texts) > 20
    for key, text in texts.items():
        assert messages.is_text_safe(text), key


def test_forbidden_phrases_detected():
    for p in messages.FORBIDDEN_MEDICAL_TERMS:
        assert not messages.is_text_safe("سلام " + p)


def test_meal_options_complete():
    for needed in ("ناشتا", "قبل از ناهار", "قبل از شروع ورزش", "بلافاصله بعد از ورزش", "قبل از خواب"):
        assert any(needed in m for m in messages.MEAL_OPTIONS)


def test_drug_bank_meals_are_valid_options_and_safe():
    import med_parser
    for d in med_parser.DRUGS:
        assert d["meal_relation"] in messages.MEAL_OPTIONS, d["name_fa"]
        assert messages.is_text_safe(d["name_fa"] + d["category"])


def test_disclaimer_present():
    assert "توصیه‌ی پزشکی نمی‌دهد" in messages.DISCLAIMER
