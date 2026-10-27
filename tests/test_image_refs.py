"""Local statement image detection; no files or remote resources are required."""
import unittest

from polygon_tool.image_refs import has_image_reference, image_reference_fields


class ImageReferenceTests(unittest.TestCase):
    def test_image_paths_in_each_statement_field(self):
        for field in ('name', 'legend', 'lengend', 'input', 'output', 'note'):
            for reference in (
                'Xem images/hinh.png.',
                r'Đường dẫn D:\đề bài\hình.JPG',
                'https://example.test/photo.JPEG?size=400#preview',
                '(diagram.svg),',
                'animation.gif', 'image.webp', 'image.bmp', 'image.tiff',
                'image.avif', 'image.heic', 'image.apng', 'image.jfif',
                'image.ico', 'image.jxl',
            ):
                with self.subTest(field=field, reference=reference):
                    self.assertEqual(image_reference_fields({field: reference}),
                                     ['legend' if field == 'lengend' else field])

    def test_markup_references_can_omit_the_extension(self):
        for reference in (
            r'\includegraphics[width=5cm]{resources/hình minh họa}',
            '<img src="/resources/diagram?id=1">',
            '![Sơ đồ](/resources/diagram)',
            '![Sơ đồ][figure]',
        ):
            with self.subTest(reference=reference):
                self.assertTrue(has_image_reference({'legend': reference}))

    def test_non_images_and_embedded_data_do_not_warn(self):
        for text in (
            '', 'Cho số nguyên n.', 'Chỉ hỗ trợ PNG và JPG.',
            'answer.cpp figure.png.exe archive.jpg.bak picture.jpeg2000',
            '<img src="data:image/png;base64,AAAA">',
            '![Sơ đồ](data:image/jpeg;base64,AAAA)',
        ):
            with self.subTest(text=text):
                self.assertFalse(has_image_reference({'note': text}))
        self.assertEqual(image_reference_fields({
            'name problem': 'not-a-statement.png',
            'checker': 'checker.png', 'gen': 'gen.jpg',
            'script_sinh_test': 'script.svg', 'solution': 'solution.webp',
        }), [])

    def test_aliases_and_repeated_paths_only_list_the_field_once(self):
        self.assertEqual(image_reference_fields({
            'lengend': 'a.png b.jpg a.png', 'legend': 'c.gif',
            'name': 'Tên', 'note': 'd.webp',
        }), ['legend', 'note'])


if __name__ == '__main__':
    unittest.main()
