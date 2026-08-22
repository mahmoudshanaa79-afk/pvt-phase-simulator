"""Reserved module for engineering unit conversions.

No conversion API is implemented yet. Current EOS APIs require the SI units
documented by each function and result model. Module 16 property rows already
use canonical K, Pa, and dimensionless units; its loader rejects other units
instead of performing an undocumented conversion.
"""
