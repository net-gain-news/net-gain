<?php
/**
 * Unit checks for Net_Gain_News_Schema::apply (the pure part of includes/class-news-schema.php).
 *
 *     php net-gain-studio/tests/news-schema-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function add_filter() {}
function home_url( $path = '' ) { return 'https://netgain.news' . $path; }
require __DIR__ . '/../includes/class-news-schema.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$img  = array( array( 'url' => 'https://x/a.webp', 'width' => 1200, 'height' => 630 ), array( 'url' => 'https://x/b.jpg', 'width' => 1280, 'height' => 720 ) );
$show = array( 'slug' => 'edtech', 'name' => 'Net Gain Edtech', 'url' => 'https://netgain.news/edtech/', 'logo' => array( 'url' => 'https://x/logo.png', 'width' => 426, 'height' => 60 ) );
$base = array(
	array( '@type' => 'WebPage', '@id' => 'p#webpage' ),
	array( '@type' => 'NewsArticle', '@id' => 'p#newsarticle', 'publisher' => array( '@id' => 'https://netgain.news/#organization' ) ),
	array( '@type' => 'Organization', '@id' => 'https://netgain.news/#organization', 'name' => 'Net Gain News' ),
);

$out = Net_Gain_News_Schema::apply( $base, array( 'images' => $img, 'show' => $show ) );
check( 'NewsArticle gets both images', count( $out[1]['image'] ) === 2 && $out[1]['image'][0]['url'] === 'https://x/a.webp' && $out[1]['image'][0]['@type'] === 'ImageObject' );
check( 'publisher is the show, not the site organization', $out[1]['publisher']['@id'] === 'https://netgain.news/#show-edtech' );
$org = end( $out );
check( 'show organization node appended with name, url and logo', $org['name'] === 'Net Gain Edtech' && $org['url'] === 'https://netgain.news/edtech/' && $org['logo']['height'] === 60 && $org['logo']['width'] === 426 );
check( 'site organization kept as parent and still in the graph', $org['parentOrganization']['@id'] === 'https://netgain.news/#organization' && $out[2]['name'] === 'Net Gain News' );
check( 'other nodes untouched', $out[0] === $base[0] && ! isset( $out[0]['image'] ) );

$no_logo = Net_Gain_News_Schema::apply( $base, array( 'images' => $img, 'show' => null ) );
check( 'no show logo: publisher left as AIOSEO set it', $no_logo[1]['publisher']['@id'] === 'https://netgain.news/#organization' && count( $no_logo ) === 3 );
check( 'no show logo: image still added', count( $no_logo[1]['image'] ) === 2 );

$no_art = Net_Gain_News_Schema::apply( $base, array( 'images' => array(), 'show' => $show ) );
check( 'no art yet: image left unset, publisher still set', ! isset( $no_art[1]['image'] ) && $no_art[1]['publisher']['@id'] === 'https://netgain.news/#show-edtech' );

$typed = array( array( '@type' => array( 'Article', 'NewsArticle' ), '@id' => 'q' ) );
check( 'array @type containing NewsArticle is recognised', isset( Net_Gain_News_Schema::apply( $typed, array( 'images' => $img, 'show' => null ) )[0]['image'] ) );

$plain = array( array( '@type' => 'WebPage', '@id' => 'w' ) );
check( 'no NewsArticle node: graph returned unchanged, no show node added', Net_Gain_News_Schema::apply( $plain, array( 'images' => $img, 'show' => $show ) ) === $plain );

echo $fail ? "FAILED: $fail\n" : "ALL PASSED\n";
exit( $fail ? 1 : 0 );
