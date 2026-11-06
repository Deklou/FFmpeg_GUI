import unittest
from compression_stats import calculate_summary, format_bytes, reduction_percentage


class CompressionStatsTests(unittest.TestCase):
    def test_before_conversion(self):
        s = calculate_summary([1200, 800], {})
        self.assertEqual(s['total_input'], 2000)
        self.assertEqual(s['known_count'], 0)
        self.assertIsNone(s['known_reduction'])

    def test_partial_results_do_not_mix_pending_inputs(self):
        s = calculate_summary([1200, 800, 1000], {0: 600, 1: 400})
        self.assertEqual(s['total_input'], 3000)
        self.assertEqual(s['known_input'], 2000)
        self.assertEqual(s['known_output'], 1000)
        self.assertEqual(s['known_reduction'], 50)

    def test_increase_is_negative_reduction(self):
        self.assertAlmostEqual(reduction_percentage(500, 650), -30.0)

    def test_zero_input_size(self):
        self.assertIsNone(reduction_percentage(0, 0))
        self.assertIsNone(calculate_summary([0], {0: 0})['known_reduction'])

    def test_filter_invalid_indices(self):
        s = calculate_summary([200], {0: 100, 4: 90})
        self.assertEqual(s['known_count'], 1)

    def test_format_size(self):
        self.assertEqual(format_bytes(1024*1024), '1.0 Mo')
        self.assertEqual(format_bytes(1024**3), '1.00 Go')


if __name__ == '__main__':
    unittest.main()
