<?php
/**
 * Unit checks for Net_Gain_News_Sitemap::build_xml (the pure part of includes/class-news-sitemap.php).
 *
 *     php net-gain-studio/tests/news-sitemap-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/class-news-sitemap.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$xml = Net_Gain_News_Sitemap::build_xml( array(
	array( 'loc' => 'https://netgain.news/edtech/a/', 'name' => 'Net Gain Edtech', 'language' => 'en', 'date' => '2026-10-09T13:56:05-07:00', 'title' => 'Teachers & "AI": a <big> day' ),
) );
$doc = simplexml_load_string( $xml );
check( 'document parses as XML', $doc !== false );
$doc->registerXPathNamespace( 's', 'http://www.sitemaps.org/schemas/sitemap/0.9' );
$doc->registerXPathNamespace( 'n', 'http://www.google.com/schemas/sitemap-news/0.9' );
check( 'one url with the right loc', (string) $doc->xpath( '//s:url/s:loc' )[0] === 'https://netgain.news/edtech/a/' );
check( 'publication name and language', (string) $doc->xpath( '//n:publication/n:name' )[0] === 'Net Gain Edtech' && (string) $doc->xpath( '//n:publication/n:language' )[0] === 'en' );
check( 'publication date is ISO 8601', (string) $doc->xpath( '//n:publication_date' )[0] === '2026-10-09T13:56:05-07:00' );
check( 'title with &, quotes and tags round-trips escaped', (string) $doc->xpath( '//n:title' )[0] === 'Teachers & "AI": a <big> day' );

$empty = simplexml_load_string( Net_Gain_News_Sitemap::build_xml( array() ) );
check( 'no recent episodes: a valid, empty urlset', $empty !== false && count( $empty->children( 'http://www.sitemaps.org/schemas/sitemap/0.9' ) ) === 0 );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
