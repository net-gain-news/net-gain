<?php
/**
 * Unit checks for the pure parts of includes/rest/class-rest-signature-strip.php.
 *
 *     php net-gain-studio/tests/signature-strip-test.php      (ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/rest/class-rest-signature-strip.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$img = imagecreatetruecolor( 40, 10 ); ob_start(); imagepng( $img ); $png = ob_get_clean();
check( 'a real PNG decodes', Net_Gain_REST_Signature_Strip::decode_png( base64_encode( $png ) ) === $png );
check( 'a JPEG is refused', null === Net_Gain_REST_Signature_Strip::decode_png( base64_encode( "\xFF\xD8\xFF\xE0" . str_repeat( 'x', 50 ) ) ) );
check( 'text that is not base64 is refused', null === Net_Gain_REST_Signature_Strip::decode_png( '%%%not base64%%%' ) );
check( 'PNG header without a valid image is refused', null === Net_Gain_REST_Signature_Strip::decode_png( base64_encode( "\x89PNG\r\n\x1a\n" . 'junk' ) ) );
check( 'an empty value and a non-string are refused', null === Net_Gain_REST_Signature_Strip::decode_png( '' ) && null === Net_Gain_REST_Signature_Strip::decode_png( array() ) );
$big = imagecreatetruecolor( 4000, 10 ); ob_start(); imagepng( $big ); $bigpng = ob_get_clean();
check( 'an over-wide PNG is refused', null === Net_Gain_REST_Signature_Strip::decode_png( base64_encode( $bigpng ) ) );
check( 'an older episode is ignored', Net_Gain_REST_Signature_Strip::is_older( '2026-10-15', '2026-10-16' ) );
check( 'the same or a newer episode is accepted', ! Net_Gain_REST_Signature_Strip::is_older( '2026-10-16', '2026-10-16' ) && ! Net_Gain_REST_Signature_Strip::is_older( '2026-10-19', '2026-10-16' ) );
check( 'nothing stored yet accepts anything', ! Net_Gain_REST_Signature_Strip::is_older( '2026-10-01', '' ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
