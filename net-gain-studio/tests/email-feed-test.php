<?php
/**
 * Unit checks for the pure card builders in includes/class-email-feed.php.
 *
 *     php net-gain-studio/tests/email-feed-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function add_action() {}
require __DIR__ . '/../includes/class-email-feed.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$e = array(
	'title'          => 'Teachers & "AI": <big> day',
	'url'            => 'https://netgain.news/edtech/a/',
	'listen_url'     => 'https://netgain.news/edtech/a/?autoplay=1',
	'transcript_url' => 'https://netgain.news/edtech/a/#transcript',
	'image_url'      => 'https://netgain.news/wp-content/uploads/art.jpg',
	'image_alt'      => 'Net Gain Edtech episode: x',
	'date_label'     => 'Oct 9, 2026',
	'summary'        => 'A Maryland school board bans student AI. Spokane widens its breach assessment.',
);
$daily = Net_Gain_Email_Feed::daily_card( $e );
$week  = Net_Gain_Email_Feed::compact_card( $e );

foreach ( array( 'daily' => $daily, 'weekly' => $week ) as $name => $html ) {
	check( "$name: Listen links to the episode page with autoplay", strpos( $html, 'href="https://netgain.news/edtech/a/?autoplay=1"' ) !== false );
	check( "$name: Transcript links to the #transcript anchor", strpos( $html, 'href="https://netgain.news/edtech/a/#transcript"' ) !== false );
	check( "$name: thumbnail is the episode art with alt text", strpos( $html, 'src="https://netgain.news/wp-content/uploads/art.jpg"' ) !== false && strpos( $html, 'alt="Net Gain Edtech episode: x"' ) !== false );
	check( "$name: title is HTML-escaped", strpos( $html, 'Teachers &amp; &quot;AI&quot;: &lt;big&gt; day' ) !== false && strpos( $html, '<big>' ) === false );
	check( "$name: well-formed enough to parse as HTML5 fragment (balanced tables)", substr_count( $html, '<table' ) === substr_count( $html, '</table>' ) );
	check( "$name: no story links, only the episode page, listen and transcript URLs", preg_match_all( '/href="([^"]+)"/', $html, $m ) && count( array_diff( array_unique( $m[1] ), array( 'https://netgain.news/edtech/a/', 'https://netgain.news/edtech/a/?autoplay=1', 'https://netgain.news/edtech/a/#transcript' ) ) ) === 0 );
}
check( 'daily: names the latest episode and shows the date', strpos( $daily, 'Latest episode' ) !== false && strpos( $daily, 'Oct 9, 2026' ) !== false );
check( 'daily: the whole phrase "Show notes and source story links" is one link to the episode page', strpos( $daily, '<a href="https://netgain.news/edtech/a/" style="color:#2f5379;text-decoration:underline;">Show notes and source story links &rarr;</a>' ) !== false );
check( 'weekly: offers a Story links link to the episode page', strpos( $week, '>Story links</a>' ) !== false );
check( 'weekly: long summaries are trimmed with an ellipsis', strpos( Net_Gain_Email_Feed::compact_card( array_merge( $e, array( 'summary' => str_repeat( 'word ', 60 ) ) ) ), '&hellip;' ) !== false );

$no_art = Net_Gain_Email_Feed::daily_card( array_merge( $e, array( 'image_url' => '' ) ) );
check( 'no art: the card still renders without an image tag', strpos( $no_art, '<img' ) === false && strpos( $no_art, 'Listen' ) !== false );
check( 'weekly: no art leaves no empty thumbnail cell', strpos( Net_Gain_Email_Feed::compact_card( array_merge( $e, array( 'image_url' => '' ) ) ), 'ng-thumb' ) === false );

check( 'K-12 gets the non-breaking hyphen, other hyphens and URLs are left alone', Net_Gain_Email_Feed::k12( 'K-12 and k-12 and K-120 re-run' ) === "K\u{2011}12 and k-12 and K-120 re-run" );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
