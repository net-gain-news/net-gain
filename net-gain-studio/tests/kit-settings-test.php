<?php
/**
 * Unit checks for Net_Gain_Kit_Settings's pure rules and the new kit_emailed step.
 *
 *     php net-gain-studio/tests/kit-settings-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
class WP_Error { public function __construct( $code = '', $message = '', $data = '' ) {} }
require __DIR__ . '/../includes/class-kit-settings.php';
require __DIR__ . '/../includes/helpers/class-step-status.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$K = 'Net_Gain_Kit_Settings';

// --- sanitizers --------------------------------------------------------------
check( 'a valid 24-hour time is kept', $K::sanitize_time( '08:00' ) === '08:00' && $K::sanitize_time( '23:59' ) === '23:59' && $K::sanitize_time( ' 07:05 ' ) === '07:05' );
check( 'an invalid time falls back to 08:00', $K::sanitize_time( '24:00' ) === '08:00' && $K::sanitize_time( '8:00' ) === '08:00' && $K::sanitize_time( '' ) === '08:00' && $K::sanitize_time( null ) === '08:00' && $K::sanitize_time( '08:60' ) === '08:00' );
check( 'a weekday key is kept, case and spaces forgiven', $K::sanitize_day( 'mon' ) === 'mon' && $K::sanitize_day( ' SUN ' ) === 'sun' );
check( 'anything else means no weekly email', $K::sanitize_day( 'monday' ) === '' && $K::sanitize_day( '' ) === '' && $K::sanitize_day( null ) === '' && $K::sanitize_day( 3 ) === '' );
check( 'a Kit id is a positive integer, else 0', $K::sanitize_id( '23806689' ) === 23806689 && $K::sanitize_id( 12 ) === 12 && $K::sanitize_id( '0' ) === 0 && $K::sanitize_id( '-4' ) === 0 && $K::sanitize_id( 'abc' ) === 0 && $K::sanitize_id( '' ) === 0 );

// --- which episodes may be emailed -----------------------------------------------
$on  = array( 'enabled' => true, 'since' => '2026-11-07 09:00:00' );
$live = function ( $at, $status = 'done' ) { return array( 'website_published' => array( 'status' => $status, 'at' => $at ) ); };

check( 'an episode that went live after sending was switched on is eligible', $K::episode_is_eligible( $on, $live( '2026-11-09 13:44:06' ) ) );
check( 'one that went live exactly then is eligible', $K::episode_is_eligible( $on, $live( '2026-11-07 09:00:00' ) ) );
check( 'one that went live before is not (no back-fill)', ! $K::episode_is_eligible( $on, $live( '2026-11-06 13:44:06' ) ) );
check( 'a degraded website publish still counts as live', $K::episode_is_eligible( $on, $live( '2026-11-09 13:44:06', 'degraded' ) ) );
check( 'an episode whose website page is not live yet is not eligible (yet)', ! $K::episode_is_eligible( $on, $live( '2026-11-09 13:44:06', 'pending' ) ) && ! $K::episode_is_eligible( $on, array() ) );
check( 'a failed website publish is not eligible', ! $K::episode_is_eligible( $on, $live( '2026-11-09 13:44:06', 'failed' ) ) );
check( 'with sending off, nothing is eligible', ! $K::episode_is_eligible( array( 'enabled' => false, 'since' => '2026-11-07 09:00:00' ), $live( '2026-11-09 13:44:06' ) ) );
check( 'with no switch-on moment recorded, nothing is eligible', ! $K::episode_is_eligible( array( 'enabled' => true, 'since' => '' ), $live( '2026-11-09 13:44:06' ) ) && ! $K::episode_is_eligible( array(), $live( '2026-11-09 13:44:06' ) ) );
check( 'a done website step with no time recorded is not eligible', ! $K::episode_is_eligible( $on, array( 'website_published' => array( 'status' => 'done', 'at' => null ) ) ) );

// --- the new step ----------------------------------------------------------------
$S = 'Net_Gain_Step_Status';
check( 'kit_emailed is the last step and a valid one', end( $S::STEPS ) === 'kit_emailed' && $S::is_valid_step( 'kit_emailed' ) );
check( 'new episodes start with it pending', $S::default_status()['kit_emailed']['status'] === 'pending' );
check( 'it cannot start before the website page is live', 'website_published' === $S::unmet_prerequisite( 'kit_emailed', array() ) );
check( 'it can start once the website page is live', null === $S::unmet_prerequisite( 'kit_emailed', array( 'website_published' => array( 'status' => 'done' ) ) ) );
$blocked = $S::apply_update( array(), 'kit_emailed', 'done' );
check( 'marking it done before the website is live is refused', $blocked instanceof WP_Error );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
