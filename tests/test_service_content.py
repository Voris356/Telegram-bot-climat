import unittest

from bot import single_line, valid_phone
from service_content import FAQ, SERVICES, build_welcome


class ServiceContentTests(unittest.TestCase):
    def test_services_cover_requested_categories(self):
        self.assertTrue(
            {"installation", "repair", "freon", "maintenance"}.issubset(SERVICES)
        )

    def test_every_service_has_a_title_and_description(self):
        for service in SERVICES.values():
            with self.subTest(service=service.title):
                self.assertTrue(service.title.strip())
                self.assertTrue(service.description.strip())

    def test_faq_answers_are_present(self):
        self.assertTrue(
            {"choose", "not_cooling", "freon", "maintenance", "price"}.issubset(FAQ)
        )
        self.assertTrue(all(answer.strip() for answer in FAQ.values()))

    def test_welcome_does_not_invent_city_or_phone(self):
        text = build_welcome("Моя компания")
        self.assertIn("Моя компания", text)
        self.assertNotIn("Телефон для связи:", text)
        self.assertNotIn("Зона обслуживания:", text)

    def test_welcome_includes_configured_business_details(self):
        text = build_welcome("Климат", "Самарканд", "+998 90 123 45 67")
        self.assertIn("Самарканд", text)
        self.assertIn("+998 90 123 45 67", text)

    def test_phone_validation_accepts_international_format(self):
        self.assertTrue(valid_phone("+998 90 123 45 67"))

    def test_phone_validation_rejects_too_short_or_non_numeric_values(self):
        self.assertFalse(valid_phone("12345"))
        self.assertFalse(valid_phone("call me"))

    def test_single_line_removes_newline_injection(self):
        self.assertEqual(single_line("имя\nНовая заявка"), "имя Новая заявка")


if __name__ == "__main__":
    unittest.main()
