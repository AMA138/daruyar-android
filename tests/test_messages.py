import messages

FORBIDDEN = ["دوز را", "قطع کنید", "افزایش دهید", "کاهش دهید", "تشخیص", "بیماری شما", "مصرف نکنید", "دو برابر"]

def test_no_medical_advice_in_texts():
    for key, text in messages.all_texts().items():
        for bad in FORBIDDEN:
            assert bad not in text, f"{key} contains forbidden phrase: {bad}"

def test_disclaimer_in_welcome():
    assert messages.DISCLAIMER in messages.WELCOME
