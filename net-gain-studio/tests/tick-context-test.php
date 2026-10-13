<?php
/**
 * Unit checks for Net_Gain_REST_Tick_Context::pending_retry_dates().
 *
 *     php net-gain-studio/tests/tick-context-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function register_rest_route() {}
require __DIR__ . '/../includes/rest/class-rest-tick-context.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$C = 'Net_Gain_REST_Tick_Context';
$a = array(
	array( 'action' => 'publish_youtube', 'status' => 'pending', 'episode_date' => '2026-10-13', 'force' => true ),
	array( 'action' => 'publish_captivate', 'status' => 'done', 'episode_date' => '2026-10-12' ),
	array( 'action' => 'generate_script', 'status' => 'pending', 'episode_date' => '2026-10-14' ),
	array( 'action' => 'generate_images', 'status' => 'pending', 'episode_date' => '2026-10-11' ),
	array( 'action' => 'publish_youtube', 'status' => 'pending' ),
	'junk',
);
$d = $C::pending_retry_dates( $a );
check( 'a pending publish_youtube keeps its episode in flight', ! empty( $d['2026-10-13'] ) );
check( 'a pending generate_images keeps its episode in flight', ! empty( $d['2026-10-11'] ) );
check( 'a finished action does not', empty( $d['2026-10-12'] ) );
check( 'generate_script is handled elsewhere and does not', empty( $d['2026-10-14'] ) );
check( 'an action with no date and junk entries are ignored', count( $d ) === 2 );
check( 'nothing pending gives an empty set', $C::pending_retry_dates( '' ) === array() && $C::pending_retry_dates( null ) === array() );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
