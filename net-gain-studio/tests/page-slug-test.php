<?php
/**
 * Unit checks for the pure part of includes/rest/class-rest-page-slug.php.
 *
 *     php net-gain-studio/tests/page-slug-test.php      (ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
define( 'HOUR_IN_SECONDS', 3600 );
require __DIR__ . '/../includes/rest/class-rest-page-slug.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$now = strtotime( '2026-10-19 20:00:00 UTC' );
check( 'a page published hours ago is fresh', Net_Gain_REST_Page_Slug::is_fresh( '2026-10-19 17:06:00', $now ) );
check( 'a page just inside 48 hours is fresh', Net_Gain_REST_Page_Slug::is_fresh( '2026-10-17 20:00:00', $now ) );
check( 'a page just past 48 hours is not', ! Net_Gain_REST_Page_Slug::is_fresh( '2026-10-17 19:59:59', $now ) );
check( 'last week\'s page is not', ! Net_Gain_REST_Page_Slug::is_fresh( '2026-10-12 14:00:00', $now ) );
check( 'an unreadable date is not fresh', ! Net_Gain_REST_Page_Slug::is_fresh( 'not a date', $now ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
