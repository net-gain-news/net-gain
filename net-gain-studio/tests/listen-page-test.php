<?php
/**
 * Unit checks for the pure parts of includes/class-listen-page.php.
 *
 *     php net-gain-studio/tests/listen-page-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function wp_parse_url( $url, $component = -1 ) { return parse_url( $url, $component ); }   // stand-in for WordPress's own
require __DIR__ . '/../includes/class-listen-page.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$fields = Net_Gain_Listen_Page::fields();

check( 'every field has a label, type, blank rule, standard wording and help', count( array_filter( $fields, function ( $f ) { return $f['label'] && in_array( $f['type'], array( 'text', 'rich' ), true ) && in_array( $f['blank'], array( 'default', 'hide' ), true ) && '' !== $f['default'] && $f['help']; } ) ) === count( $fields ) );
check( 'no two sections share a field key', count( $fields ) === array_sum( array_map( function ( $s ) { return count( $s['fields'] ); }, Net_Gain_Listen_Page::sections() ) ) );

$copy = Net_Gain_Listen_Page::resolve( array(), $fields );
check( 'nothing saved gives the standard wording', $copy['headline'] === $fields['headline']['default'] );

$copy = Net_Gain_Listen_Page::resolve( array( 'headline' => 'My headline' ), $fields );
check( 'saved wording wins', 'My headline' === $copy['headline'] && $copy['lede'] === $fields['lede']['default'] );

$copy = Net_Gain_Listen_Page::resolve( array( 'headline' => '   ' ), $fields );
check( 'an emptied required box falls back to the standard wording', $copy['headline'] === $fields['headline']['default'] );

$copy = Net_Gain_Listen_Page::resolve( array( 'eyebrow' => '' ), $fields );
check( 'an emptied optional box stays empty (the element is hidden)', '' === $copy['eyebrow'] );

$copy = Net_Gain_Listen_Page::resolve( array( 'why_text' => '' ), $fields );
check( 'the why section can be removed by emptying its text', '' === $copy['why_text'] && $copy['why_heading'] === $fields['why_heading']['default'] );

$copy = Net_Gain_Listen_Page::resolve( array( 'headline' => array( 'x' ), 'bogus' => 'x' ), $fields );
check( 'junk values and unknown keys are ignored', $copy['headline'] === $fields['headline']['default'] && ! isset( $copy['bogus'] ) );

$store = Net_Gain_Listen_Page::to_store( array( 'headline' => ' New one ', 'lede' => $fields['lede']['default'], 'eyebrow' => '', 'nope' => 'x', 'button' => 5 ), $fields );
ksort( $store );
check( 'only changed wording is stored, trimmed', $store === array( 'eyebrow' => '', 'headline' => 'New one' ) );

check( 'K-12 gets the non-breaking hyphen', Net_Gain_Listen_Page::k12( 'the K-12 news, not K-123' ) === "the K\u{2011}12 news, not K-123" );
check( 'the standard headline renders with it', false !== strpos( Net_Gain_Listen_Page::k12( $fields['headline']['default'] ), "K\u{2011}12" ) );

$robots = "User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n\nSitemap: https://netgain.news/sitemap.xml";
$out    = Net_Gain_Listen_Page::robots_with_disallow( $robots, array( '/edtech/listen/' ) );
check( 'the Disallow goes inside the existing everyone group', strpos( $out, "User-agent: *\nDisallow: /edtech/listen/\nDisallow: /wp-admin/" ) === 0 );
check( 'the sitemap line is kept', false !== strpos( $out, 'Sitemap: https://netgain.news/sitemap.xml' ) );
check( 'adding it twice does not repeat it', substr_count( Net_Gain_Listen_Page::robots_with_disallow( $out, array( '/edtech/listen/' ) ), 'Disallow: /edtech/listen/' ) === 1 );
check( 'no paths leaves robots.txt alone', Net_Gain_Listen_Page::robots_with_disallow( $robots, array() ) === $robots );
check( 'a robots.txt with no everyone group gets one', false !== strpos( Net_Gain_Listen_Page::robots_with_disallow( "Sitemap: x\n", array( 'edtech/listen' ) ), "User-agent: *\nDisallow: /edtech/listen/" ) );
check( 'the site root is never disallowed', Net_Gain_Listen_Page::robots_with_disallow( $robots, array( '/', '' ) ) === $robots );
check( 'path of a permalink', Net_Gain_Listen_Page::path_of( 'https://netgain.news/edtech/listen/' ) === '/edtech/listen/' );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
