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

check( 'image path is recognised', Net_Gain_REST_Signature_Strip::image_request( 'ng-signature/edtech-strip-dark.png' ) === array( 'edtech', 'dark' ) );
check( 'hyphenated show slug in the image path', Net_Gain_REST_Signature_Strip::image_request( '/ng-signature/real-estate-strip-light.png/' ) === array( 'real-estate', 'light' ) );
check( 'other paths and traversal are not images', null === Net_Gain_REST_Signature_Strip::image_request( 'ng-signature/../wp-config.php' ) && null === Net_Gain_REST_Signature_Strip::image_request( 'ng-signature/edtech-strip-blue.png' ) && null === Net_Gain_REST_Signature_Strip::image_request( 'wp-content/uploads/ng-signature/edtech-strip-light.png' ) );
$v = Net_Gain_REST_Signature_Strip::validators( 18628, 1792000000 );
check( 'validators carry a quoted etag and an HTTP date', 0 === strpos( $v['etag'], '"' ) && substr( $v['last_modified'], -4 ) === ' GMT' );
check( 'a changed file has a different etag', $v['etag'] !== Net_Gain_REST_Signature_Strip::validators( 18700, 1792000000 )['etag'] && $v['etag'] !== Net_Gain_REST_Signature_Strip::validators( 18628, 1792000100 )['etag'] );
check( 'matching etag is not modified', Net_Gain_REST_Signature_Strip::is_not_modified( $v['etag'], '', $v['etag'], 1792000000 ) );
check( 'stale etag is modified, even if the date would match', ! Net_Gain_REST_Signature_Strip::is_not_modified( '"old"', $v['last_modified'], $v['etag'], 1792000000 ) );
check( 'date-only validation: newer file is modified, same is not', ! Net_Gain_REST_Signature_Strip::is_not_modified( '', gmdate( 'D, d M Y H:i:s', 1791999000 ) . ' GMT', $v['etag'], 1792000000 ) && Net_Gain_REST_Signature_Strip::is_not_modified( '', $v['last_modified'], $v['etag'], 1792000000 ) );
check( 'no validators sent is modified', ! Net_Gain_REST_Signature_Strip::is_not_modified( '', '', $v['etag'], 1792000000 ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
