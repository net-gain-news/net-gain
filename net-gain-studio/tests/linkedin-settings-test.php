<?php
/**
 * Unit checks for Net_Gain_LinkedIn_Settings's pure rules and the linkedin_posted step.
 *
 *     php net-gain-studio/tests/linkedin-settings-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
class WP_Error { public function __construct( $code = '', $message = '', $data = '' ) {} }
require __DIR__ . '/../includes/class-kit-settings.php';
require __DIR__ . '/../includes/class-linkedin-settings.php';
require __DIR__ . '/../includes/helpers/class-step-status.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$L = 'Net_Gain_LinkedIn_Settings';

// --- the page id --------------------------------------------------------------
check( 'a bare number is the page id', $L::sanitize_page_id( '146769492' ) === 146769492 && $L::sanitize_page_id( ' 146769492 ' ) === 146769492 && $L::sanitize_page_id( 146769492 ) === 146769492 );
check( 'a showcase address gives its number', $L::sanitize_page_id( 'https://www.linkedin.com/showcase/146769492/' ) === 146769492 && $L::sanitize_page_id( 'linkedin.com/showcase/146769492' ) === 146769492 );
check( 'a company address gives its number, with or without a tail', $L::sanitize_page_id( 'https://www.linkedin.com/company/146874938/' ) === 146874938 && $L::sanitize_page_id( 'https://www.linkedin.com/company/146874938/admin/?x=1' ) === 146874938 && $L::sanitize_page_id( 'https://www.linkedin.com/company/146874938?trk=a' ) === 146874938 );
check( 'a name-only address has no id', $L::sanitize_page_id( 'https://www.linkedin.com/company/net-gain-news/' ) === 0 && $L::sanitize_page_id( 'https://www.linkedin.com/showcase/net-gain-edtech/' ) === 0 );
check( 'junk is 0', $L::sanitize_page_id( '' ) === 0 && $L::sanitize_page_id( null ) === 0 && $L::sanitize_page_id( 'abc' ) === 0 && $L::sanitize_page_id( '12' ) === 0 && $L::sanitize_page_id( 'https://evil.test/company/146874938/' ) === 0 && $L::sanitize_page_id( array( 1 ) ) === 0 );

// --- the show's hashtags -------------------------------------------------------
check( 'hashtags split on spaces, commas and newlines; # optional', $L::sanitize_hashtags( '#education edtech,K12' . "\n" . '#AI' ) === array( 'education', 'edtech', 'K12', 'AI' ) );
check( 'K-12 becomes K12 (ordinary or non-breaking hyphen)', $L::sanitize_hashtags( 'K-12' ) === array( 'K12' ) && $L::sanitize_hashtags( "K\u{2011}12" ) === array( 'K12' ) );
check( 'repeats in any case are dropped, junk is dropped', $L::sanitize_hashtags( 'edtech EdTech !!! # ed-tech' ) === array( 'edtech', 'edtech' ) || $L::sanitize_hashtags( 'edtech EdTech' ) === array( 'edtech' ) );
check( 'at most ten, each at most thirty characters', count( $L::sanitize_hashtags( 'a1 a2 a3 a4 a5 a6 a7 a8 a9 a10 a11 a12' ) ) === 10 && strlen( $L::sanitize_hashtags( str_repeat( 'x', 50 ) )[0] ) === 30 );
check( 'nothing usable gives an empty list', $L::sanitize_hashtags( '' ) === array() && $L::sanitize_hashtags( null ) === array() && $L::sanitize_hashtags( '### ,,' ) === array() );

// --- which episodes may be posted -----------------------------------------------
$on   = array( 'enabled' => true, 'since' => '2026-11-20 09:00:00', 'page_id' => 146769492 );
$live = function ( $at, $status = 'done' ) { return array( 'website_published' => array( 'status' => $status, 'at' => $at ) ); };
check( 'an episode live after switch-on is eligible', $L::episode_is_eligible( $on, $live( '2026-11-20 21:44:06' ) ) );
check( 'one live before switch-on is not (no back-fill)', ! $L::episode_is_eligible( $on, $live( '2026-11-19 21:44:06' ) ) );
check( 'with posting off, nothing is eligible', ! $L::episode_is_eligible( array( 'enabled' => false, 'since' => '2026-11-20 09:00:00' ), $live( '2026-11-20 21:44:06' ) ) );
check( 'an episode whose page is not live yet is not eligible', ! $L::episode_is_eligible( $on, $live( '2026-11-20 21:44:06', 'pending' ) ) && ! $L::episode_is_eligible( $on, array() ) );
check( 'a show that is on with no page set stays eligible, so the pipeline can report it', $L::episode_is_eligible( array( 'enabled' => true, 'since' => '2026-11-20 09:00:00', 'page_id' => 0 ), $live( '2026-11-20 21:44:06' ) ) );

// --- the step -------------------------------------------------------------------
$S = 'Net_Gain_Step_Status';
check( 'linkedin_posted is a valid step and starts pending', $S::is_valid_step( 'linkedin_posted' ) && $S::default_status()['linkedin_posted']['status'] === 'pending' );
check( 'it cannot start before the website page is live', 'website_published' === $S::unmet_prerequisite( 'linkedin_posted', array() ) );
check( 'it can start once the page is live, whatever YouTube or the email did', null === $S::unmet_prerequisite( 'linkedin_posted', array( 'website_published' => array( 'status' => 'done' ), 'youtube_published' => array( 'status' => 'failed' ) ) ) );
check( 'marking it done before the page is live is refused', $S::apply_update( array(), 'linkedin_posted', 'done' ) instanceof WP_Error );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
