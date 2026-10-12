<?php
/**
 * Unit checks for the pure parts of includes/class-public-surface.php.
 *
 *     php net-gain-studio/tests/public-surface-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function add_filter() {}
function add_action() {}
function remove_action() {}
require __DIR__ . '/../includes/class-public-surface.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$S = 'Net_Gain_Public_Surface';
foreach ( array( '/wp/v2/ng_episode', '/wp/v2/ng_episode/330', '/wp/v2/ng_show', '/wp/v2/ng_show/16', '/wp/v2/ng_vertical', '/wp/v2/users', '/wp/v2/users/3', '/wp/v2/users/me' ) as $r ) {
	check( "private: $r", $S::is_private_route( $r ) );
}
foreach ( array( '/wp/v2/podcast', '/wp/v2/pages/77', '/wp/v2/media', '/wp/v2/search', '/net-gain/v1/tick-context', '/', '/wp/v2/ng_episodes_extra', '/wp/v2/usersx' ) as $r ) {
	check( "not private: $r", ! $S::is_private_route( $r ) );
}

check( 'a talent-role user is an anchor', $S::is_anchor( array( 'ng_talent' ), array(), 0 ) );
check( 'a user with a show assignment is an anchor', $S::is_anchor( array( 'subscriber' ), array( array( 'id' => 1 ) ), 0 ) );
check( 'a user with a published episode is an anchor', $S::is_anchor( array( 'editor' ), array(), 2 ) );
check( 'the administrator with no episodes is not an anchor', ! $S::is_anchor( array( 'administrator' ), array(), 0 ) );
check( 'the service account is not an anchor', ! $S::is_anchor( array( 'ng_service' ), array(), 0 ) );

foreach ( array( '/podcast/', '/podcast', 'podcast/', '/podcast/page/2/', '/ssp-podcast-archive/', '/ssp-podcast-archive' ) as $p ) {
	check( "duplicate archive path: $p", $S::is_duplicate_archive_path( $p ) );
}
foreach ( array( '/edtech/episodes/', '/feed/podcast/', '/podcast-download/335/x', '/podcast/frederick-county-bans/', '/podcasts/', '/' ) as $p ) {
	check( "not a duplicate archive path: $p", ! $S::is_duplicate_archive_path( $p ) );
}

$feeds = array( 'edtech' => 'https://feeds.captivate.fm/netgain-edtech/' );
check( 'the edtech slug maps to its Captivate feed', 'https://feeds.captivate.fm/netgain-edtech/' === $S::podcast_feed_target( 'edtech', $feeds ) );
check( 'no slug maps to the only show', 'https://feeds.captivate.fm/netgain-edtech/' === $S::podcast_feed_target( '', $feeds ) );
check( 'an unknown slug has no feed', null === $S::podcast_feed_target( 'net-gain-news', $feeds ) );
check( 'no slug with several shows has no feed', null === $S::podcast_feed_target( '', $feeds + array( 'real-estate' => 'https://feeds.captivate.fm/x/' ) ) );
check( 'a slug with no shows configured has no feed', null === $S::podcast_feed_target( 'edtech', array() ) );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
