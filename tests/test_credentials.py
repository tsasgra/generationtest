from pathlib import Path
import tempfile
import unittest

from polygon_tool.credentials import load_credentials


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '.env'

    def test_bom_crlf_quotes_comments_and_export(self):
        self.path.write_bytes(b'\xef\xbb\xbf# local\r\nexport POLYGON_API_KEY="local-key"\r\nPOLYGON_API_SECRET=\'local-secret\'\r\n')
        environment = {}
        self.assertEqual(load_credentials(self.path, environment), ('local-key', 'local-secret'))
        self.assertEqual(environment, {})

    def test_environment_overrides_file_and_missing_value_falls_back(self):
        self.path.write_text('POLYGON_API_KEY=file-key\nPOLYGON_API_SECRET=file-secret\n')
        self.assertEqual(load_credentials(self.path, {'POLYGON_API_KEY': 'env-key'}), ('env-key', 'file-secret'))
        self.path.write_bytes(b'\xff')
        self.assertEqual(load_credentials(self.path, {'POLYGON_API_KEY': 'env-key', 'POLYGON_API_SECRET': 'env-secret'}),
                         ('env-key', 'env-secret'))

    def test_missing_credentials_names_variables_without_values(self):
        with self.assertRaisesRegex(ValueError, 'Thiếu POLYGON_API_KEY/POLYGON_API_SECRET'):
            load_credentials(self.path, {})

    def test_invalid_syntax_does_not_echo_values(self):
        for value in ('POLYGON_API_KEY="sensitive-unclosed', 'sensitive-unparsed',
                      'POLYGON_API_KEY=first\nPOLYGON_API_KEY=sensitive-duplicate'):
            self.path.write_text(value)
            with self.assertRaises(ValueError) as error:
                load_credentials(self.path, {})
            self.assertNotIn('sensitive', str(error.exception))

    def test_values_are_literal_not_shell_or_variable_expansion(self):
        self.path.write_text('POLYGON_API_KEY=$(echo ignored)\nPOLYGON_API_SECRET=${OTHER_SECRET}\n')
        self.assertEqual(load_credentials(self.path, {}), ('$(echo ignored)', '${OTHER_SECRET}'))

    def test_invalid_utf8_is_clear_error(self):
        self.path.write_bytes(b'\xff')
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            load_credentials(self.path, {})


if __name__ == '__main__':
    unittest.main()
