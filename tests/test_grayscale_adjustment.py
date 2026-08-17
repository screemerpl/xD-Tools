from PySide6.QtGui import QColor, QImage

from mdtools.grayscale import apply_grayscale, brightness_contrast_lut


def test_identity_lut_is_a_no_op():
    assert brightness_contrast_lut(0, 0) == bytes(range(256))


def test_lut_is_clamped_to_the_documented_range():
    # out-of-range inputs must not invert or otherwise misbehave -- they
    # clamp to the same LUT as the nearest in-range value
    assert brightness_contrast_lut(500, 0) == brightness_contrast_lut(100, 0)
    assert brightness_contrast_lut(-500, 0) == brightness_contrast_lut(-100, 0)


def test_apply_grayscale_desaturates_and_preserves_alpha(qt_app):
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor(200, 50, 50, 255))
    image.setPixelColor(0, 0, QColor(0, 0, 0, 0))

    result = apply_grayscale(image)

    solid = result.pixelColor(1, 1)
    assert solid.red() == solid.green() == solid.blue()
    assert solid.alpha() == 255
    assert result.pixelColor(0, 0).alpha() == 0


def test_positive_brightness_lightens_the_image(qt_app):
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor(100, 100, 100, 255))

    baseline = apply_grayscale(image).pixelColor(0, 0).red()
    brighter = apply_grayscale(image, brightness=50).pixelColor(0, 0).red()

    assert brighter > baseline


def test_negative_brightness_darkens_the_image(qt_app):
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor(100, 100, 100, 255))

    baseline = apply_grayscale(image).pixelColor(0, 0).red()
    darker = apply_grayscale(image, brightness=-50).pixelColor(0, 0).red()

    assert darker < baseline


def test_contrast_pushes_a_below_mid_gray_value_further_from_mid_gray(qt_app):
    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor(90, 90, 90, 255))  # below 128 (mid gray) after conversion

    baseline = apply_grayscale(image).pixelColor(0, 0).red()
    more_contrast = apply_grayscale(image, contrast=50).pixelColor(0, 0).red()

    assert more_contrast < baseline  # further from 128, i.e. darker


def test_zero_adjustment_matches_plain_grayscale_conversion(qt_app):
    image = QImage(3, 3, QImage.Format.Format_ARGB32)
    image.fill(QColor(123, 45, 200, 255))

    plain = apply_grayscale(image)
    explicit_zero = apply_grayscale(image, brightness=0, contrast=0)

    assert plain.pixelColor(1, 1) == explicit_zero.pixelColor(1, 1)
