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
$logo = array( 'url' => 'https://x/logo.png', 'width' => 400, 'height' => 60 );
$base = array(
	array( '@type' => 'WebPage', '@id' => 'p#webpage' ),
	array( '@type' => 'NewsArticle', '@id' => 'p#newsarticle', 'publisher' => array( '@id' => 'https://netgain.news/#organization' ) ),
	array( '@type' => 'Organization', '@id' => 'https://netgain.news/#organization', 'name' => 'Net Gain News' ),
);

$out = Net_Gain_News_Schema::apply( $base, array( 'images' => $img, 'logo' => $logo ) );
check( 'NewsArticle gets both images as ImageObjects', count( $out[1]['image'] ) === 2 && $out[1]['image'][0]['url'] === 'https://x/a.webp' && $out[1]['image'][0]['@type'] === 'ImageObject' );
check( 'publisher stays the site organization (Net Gain News)', $out[1]['publisher']['@id'] === 'https://netgain.news/#organization' );
check( 'no show organization node is added', count( $out ) === 3 );
check( 'site organization gains the logo', $out[2]['logo']['url'] === 'https://x/logo.png' && $out[2]['logo']['height'] === 60 && $out[2]['name'] === 'Net Gain News' );
check( 'other nodes untouched', $out[0] === $base[0] );

$has_logo       = $base;
$has_logo[2]['logo'] = 'https://aioseo/own-logo.png';
$kept = Net_Gain_News_Schema::apply( $has_logo, array( 'images' => $img, 'logo' => $logo ) );
check( 'an organization logo set in AIOSEO is never overwritten', $kept[2]['logo'] === 'https://aioseo/own-logo.png' );

$no_logo = Net_Gain_News_Schema::apply( $base, array( 'images' => $img, 'logo' => null ) );
check( 'no logo setting: organization untouched, image still added', ! isset( $no_logo[2]['logo'] ) && count( $no_logo[1]['image'] ) === 2 );

$no_art = Net_Gain_News_Schema::apply( $base, array( 'images' => array(), 'logo' => $logo ) );
check( 'no art yet: image left unset, logo still added', ! isset( $no_art[1]['image'] ) && isset( $no_art[2]['logo'] ) );

$typed = array( array( '@type' => array( 'Article', 'NewsArticle' ), '@id' => 'q' ) );
check( 'array @type containing NewsArticle is recognised', isset( Net_Gain_News_Schema::apply( $typed, array( 'images' => $img, 'logo' => null ) )[0]['image'] ) );

$plain = array( array( '@type' => 'WebPage', '@id' => 'w' ) );
check( 'no NewsArticle or organization node: graph returned unchanged', Net_Gain_News_Schema::apply( $plain, array( 'images' => $img, 'logo' => $logo ) ) === $plain );

$crumbs = array(
	array( 'name' => 'Home', 'url' => 'https://netgain.news/' ),
	array( 'name' => 'Net Gain Edtech', 'url' => 'https://netgain.news/edtech/' ),
	array( 'name' => 'Newscasts', 'url' => 'https://netgain.news/edtech/episodes/' ),
	array( 'name' => 'Today', 'url' => '' ),
);
$with_trail = array_merge( $base, array( array( '@type' => 'BreadcrumbList', '@id' => 'p#bc', 'itemListElement' => array( array( 'name' => 'Episode', 'item' => 'https://netgain.news/podcast/' ) ) ) ) );
$out        = Net_Gain_News_Schema::apply( $with_trail, array( 'images' => array(), 'logo' => null, 'breadcrumbs' => $crumbs ) );
$list       = $out[3]['itemListElement'];
check( 'breadcrumbs: rewritten to Home > show > Newscasts > episode', count( $list ) === 4 && $list[1]['item'] === 'https://netgain.news/edtech/' && $list[2]['item'] === 'https://netgain.news/edtech/episodes/' );
check( 'breadcrumbs: no crumb points at the /podcast/ or /series/ archives', strpos( json_encode( $list ), '/podcast/' ) === false && strpos( json_encode( $list ), '/series/' ) === false );
check( 'breadcrumbs: positions run 1..4 and the last crumb has no link', $list[0]['position'] === 1 && $list[3]['position'] === 4 && ! isset( $list[3]['item'] ) );
check( 'breadcrumbs: untouched when no trail is supplied', Net_Gain_News_Schema::apply( $with_trail, array( 'images' => array(), 'logo' => null, 'breadcrumbs' => array() ) ) === $with_trail );

$described = Net_Gain_News_Schema::apply( $base, array( 'images' => array(), 'logo' => null, 'description' => 'A Maryland school board bans student AI.' ) );
check( 'description: added to the NewsArticle', $described[1]['description'] === 'A Maryland school board bans student AI.' );
check( 'description: not added to other nodes', ! isset( $described[0]['description'] ) && ! isset( $described[2]['description'] ) );
$own = $base;
$own[1]['description'] = 'AIOSEO wrote this';
check( 'description: one AIOSEO already set is never overwritten', Net_Gain_News_Schema::apply( $own, array( 'images' => array(), 'logo' => null, 'description' => 'Ours' ) )[1]['description'] === 'AIOSEO wrote this' );
check( 'description: an empty description adds nothing', ! isset( Net_Gain_News_Schema::apply( $base, array( 'images' => array(), 'logo' => null, 'description' => '' ) )[1]['description'] ) );

// Audio and headquarters
$audio = array( 'url' => 'https://x/ep.mp3', 'seconds' => 254, 'mime' => 'audio/mpeg' );
$hq    = Net_Gain_News_Schema::headquarters();
$base2 = $base;
$base2[1]['@id'] = 'https://netgain.news/edtech/ep/#newsarticle';
$base2[1]['headline'] = 'Headline';
$base2[1]['description'] = 'Desc';
$base2[1]['datePublished'] = '2026-10-16T14:16:10-07:00';
$withaudio = Net_Gain_News_Schema::apply( $base2, array( 'audio' => $audio, 'address' => $hq ) );
$ao = $withaudio[1]['audio'];
check( 'NewsArticle gets an AudioObject', $ao['@type'] === 'AudioObject' && $ao['contentUrl'] === 'https://x/ep.mp3' && $ao['encodingFormat'] === 'audio/mpeg' );
check( 'AudioObject duration is ISO 8601 from the file length', $ao['duration'] === 'PT4M14S' );
check( 'AudioObject takes name, description and upload date from the article', $ao['name'] === 'Headline' && $ao['description'] === 'Desc' && $ao['uploadDate'] === '2026-10-16T14:16:10-07:00' );
check( 'AudioObject id hangs off the article page', $ao['@id'] === 'https://netgain.news/edtech/ep/#audio' );
check( 'organization gets region and country only', $withaudio[2]['address'] === array( '@type' => 'PostalAddress', 'addressRegion' => 'BC', 'addressCountry' => 'CA' ) );
$noaudio = Net_Gain_News_Schema::apply( $base2, array( 'audio' => null ) );
check( 'no audio yet: no audio node, no address unless supplied', ! isset( $noaudio[1]['audio'] ) && ! isset( $noaudio[2]['address'] ) );
$own = $base2; $own[2]['address'] = 'kept';
check( 'an address set elsewhere is never overwritten', Net_Gain_News_Schema::apply( $own, array( 'address' => $hq ) )[2]['address'] === 'kept' );
check( 'iso_duration: exact minutes', Net_Gain_News_Schema::iso_duration( 300 ) === 'PT5M' );
check( 'iso_duration: hours', Net_Gain_News_Schema::iso_duration( 3725 ) === 'PT1H2M5S' );
check( 'iso_duration: unknown length gives nothing', Net_Gain_News_Schema::iso_duration( 0 ) === '' );
check( 'audio object without a length omits duration', ! isset( Net_Gain_News_Schema::audio_object( array( 'url' => 'u', 'seconds' => 0, 'mime' => 'audio/mpeg' ), array( 'id' => 'i', 'name' => 'n' ) )['duration'] ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
