<?php
/**
 * Unit checks for includes/class-timezones.php.
 *
 *     php net-gain-studio/tests/timezones-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
$GLOBALS['meta']      = array();
$GLOBALS['site_zone'] = 'America/Vancouver';
function get_post_meta( $id, $key, $single = false ) { return $GLOBALS['meta'][ $id ][ $key ] ?? ''; }
function wp_timezone_string() { return $GLOBALS['site_zone']; }
function esc_html( $v ) { return htmlspecialchars( $v ); }
function esc_attr( $v ) { return htmlspecialchars( $v ); }
function selected( $a, $b, $echo = true ) { return (string) $a === (string) $b ? ' selected="selected"' : ''; }
require __DIR__ . '/../includes/class-timezones.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$T = 'Net_Gain_Timezones';
check( 'a named zone is valid', $T::is_valid( 'America/New_York' ) && $T::is_valid( 'UTC' ) );
foreach ( array( 'UTC-5', 'UTC+5:30', '-05:00', 'Eastern', '', 'America/Nowhere' ) as $bad ) {
	check( "not valid: '$bad'", ! $T::is_valid( $bad ) );
}
check( 'sanitize keeps a valid zone', 'Europe/London' === $T::sanitize( ' Europe/London ' ) );
check( 'sanitize turns an offset into blank (inherit)', '' === $T::sanitize( 'UTC-5' ) );
check( 'sanitize turns junk and non-strings into blank', '' === $T::sanitize( '<script>' ) && '' === $T::sanitize( null ) && '' === $T::sanitize( array( 'x' ) ) );

check( 'the site zone is used when it is a named zone', 'America/Vancouver' === $T::site() );
$GLOBALS['site_zone'] = '-07:00';
check( 'a manual-offset site setting falls back to UTC', 'UTC' === $T::site() );
$GLOBALS['site_zone'] = 'America/Vancouver';

$GLOBALS['meta'][1] = array();
check( 'no setting: script zone inherits the site zone', 'America/Vancouver' === $T::script_zone( 1 ) && '' === $T::stored_script_zone( 1 ) );
$GLOBALS['meta'][2] = array( 'ng_recording_timezone' => 'America/Vancouver' );
check( 'an existing show keeps its retired zone until one is picked', 'America/Vancouver' === $T::script_zone( 2 ) );
$GLOBALS['meta'][3] = array( 'ng_recording_timezone' => 'America/Vancouver', 'ng_script_timezone' => 'America/New_York' );
check( 'the new script zone wins over the retired field', 'America/New_York' === $T::script_zone( 3 ) );
$GLOBALS['meta'][4] = array( 'ng_script_timezone' => 'UTC-5', 'ng_recording_timezone' => 'UTC+2' );
check( 'stored offsets are ignored, never passed to the pipeline', 'America/Vancouver' === $T::script_zone( 4 ) );
$GLOBALS['meta'][5] = array( 'ng_publish_timezone' => 'America/New_York' );
check( 'publish zone: own choice', 'America/New_York' === $T::publish_zone( 5 ) );
check( 'publish zone: blank inherits the site zone', 'America/Vancouver' === $T::publish_zone( 1 ) );

$html = $T::select_options( 'America/New_York' );
check( 'select: inherit option first and labelled with the site zone', 0 === strpos( $html, '<option value="" ' ) || 0 === strpos( $html, '<option value="">' ) );
check( 'select: inherit option names the site zone', false !== strpos( $html, 'WordPress site timezone (America/Vancouver)' ) );
check( 'select: New York is present and selected', false !== strpos( $html, '<option value="America/New_York" selected="selected">New York</option>' ) );
check( 'select: nothing else selected', 1 === substr_count( $html, 'selected="selected"' ) );
check( 'select: no fixed offsets offered', false === strpos( $html, 'value="UTC-' ) && false === strpos( $html, 'value="UTC+' ) );
check( 'select: blank selection selects the inherit option', false !== strpos( $T::select_options( '' ), '<option value="" selected="selected">' ) );

check( 'now label reads like "4:35 pm EST (UTC-05:00)"', 1 === preg_match( '/^\d{1,2}:\d{2} (am|pm) \S+ \(UTC[+-]\d{2}:\d{2}\)$/', $T::now_label( 'America/New_York' ) ) );
check( 'now label tolerates a bad zone', 0 === strpos( $T::now_label( 'nope' ), '' ) && false !== strpos( $T::now_label( 'nope' ), '(UTC+00:00)' ) );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
