import unittest

from polygon_tool.samples import detect_sample_indices, is_sample_command, parse_sample_indices


class SampleTests(unittest.TestCase):
    def test_sample_forms(self):
        for command in ("gen sample 1 > $", "gen --mode=sample --id=2 > $", 'gen --mode="sample" > 9', "gen --mode sample"):
            with self.subTest(command=command):
                self.assertTrue(is_sample_command(command))

    def test_non_sample_and_output_filename_do_not_match(self):
        for command in ("gen nonsample 1", "gen not_sample 1", "gen --mode=not_sample", "gen sample.txt", "sample random 1", "gen normal > sample", "gen normal # sample", "gen --mode=sample-extra"):
            with self.subTest(command=command):
                self.assertFalse(is_sample_command(command))

    def test_uses_expanded_indices_after_freemarker(self):
        tests = [
            {"index": 42, "manual": False, "scriptLine": "gen random 2 > 42"},
            {"index": 21, "manual": False, "scriptLine": "gen sample 1 > 21"},
            {"index": 50, "manual": False, "scriptLine": "gen --mode=sample --id=2 > 50"},
        ]
        self.assertEqual(detect_sample_indices(tests), [21, 50])

    def test_explicit_indices_override_detection(self):
        tests = [
            {"index": 2, "manual": False, "scriptLine": "gen sample 1"},
            {"index": 9, "manual": True, "input": "2 3"},
        ]
        self.assertEqual(detect_sample_indices(tests, [9]), [9])
        self.assertEqual(detect_sample_indices(tests, "9,2"), [2, 9])

    def test_manual_content_is_not_a_generator_command(self):
        with self.assertRaisesRegex(ValueError, "Không xác định"):
            detect_sample_indices([{"index": 1, "manual": True, "input": "gen sample 1"}])

    def test_absent_explicit_index_rejected(self):
        with self.assertRaisesRegex(ValueError, "Không có test.*8"):
            detect_sample_indices([{"index": 1}], [8])

    def test_invalid_indices_rejected(self):
        for value in ("", "0", "-1", "1,1", "1,abc", "1,", "1-5", "1.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_sample_indices(value)

    def test_no_automatic_first_test_fallback(self):
        with self.assertRaisesRegex(ValueError, "sample-indices"):
            detect_sample_indices([{"index": 1, "scriptLine": "gen nonsample"}])

    def test_empty_and_duplicate_server_tests_rejected(self):
        for tests in ([], [{"index": 1}, {"index": 1}], [{"index": True}], [{"index": "1"}]):
            with self.subTest(tests=tests), self.assertRaises(ValueError):
                detect_sample_indices(tests)


if __name__ == "__main__":
    unittest.main()
