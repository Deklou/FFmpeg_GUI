import unittest
from conversion_time import format_duration, parse_speed, parse_out_time, estimate_remaining, format_reduction

class TestTime(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_duration(3661), '01:01:01')
        self.assertEqual(format_duration(None), '—')
    def test_speed(self):
        self.assertEqual(parse_speed('1.23x'), 1.23)
        self.assertIsNone(parse_speed('N/A'))
        self.assertIsNone(parse_speed('0x'))
    def test_out_time(self):
        self.assertEqual(parse_out_time({'out_time_us':'12345678'}), 12.345678)
        self.assertEqual(parse_out_time({'out_time':'00:00:14.500'}),14.5)
    def test_eta(self):
        self.assertAlmostEqual(estimate_remaining(100,20,2),40)
        self.assertIsNone(estimate_remaining(None,20,2))
    def test_reduction(self):
        self.assertEqual(format_reduction(44.2),'44.2 %')
        self.assertEqual(format_reduction(-30.0),'-30.0 %')

if __name__=='__main__':unittest.main()
