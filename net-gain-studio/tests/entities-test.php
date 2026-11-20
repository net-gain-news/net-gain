<?php
/**
 * Unit checks for the pure parts of includes/class-entities.php and class-topic-pages.php.
 *
 *     php net-gain-studio/tests/entities-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
define( 'DAY_IN_SECONDS', 86400 );      // WordPress's own constant
function mysql2date( $format, $date ) { return date( $format, strtotime( $date ) ); }   // stand-in for WordPress's own
require __DIR__ . '/../includes/class-entities.php';
require __DIR__ . '/../includes/class-topic-pages.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }
function tag( $name, $kind = 'company', $note = 'n' ) { return array( 'name' => $name, 'slug' => strtolower( str_replace( ' ', '-', $name ) ), 'kind' => $kind, 'note' => $note ); }
function ptag( $name, $parent = '', $level = '', $note = 'n' ) { $t = tag( $name, 'place', $note ); $t['parent'] = $parent; $t['level'] = $level; return $t; }
function ep( $id, $date, $tags, $show = 'edtech' ) { return array( 'id' => $id, 'title' => "Ep $id", 'url' => "https://x.test/$id/", 'date' => $date, 'ts' => strtotime( $date ), 'show' => $show, 'entities' => $tags ); }

// clean_tags
$clean = Net_Gain_Entities::clean_tags( array( tag( 'Frontline' ), tag( 'Frontline' ), array( 'name' => 'Bad', 'slug' => 'Bad Slug', 'kind' => 'company' ), array( 'name' => 'X', 'slug' => 'x', 'kind' => 'person' ), 'junk', array( 'name' => '', 'slug' => 'e', 'kind' => 'topic' ) ) );
check( 'clean_tags keeps one well-formed tag', count( $clean ) === 1 && 'frontline' === $clean[0]['slug'] );
check( 'clean_tags tolerates non-arrays', array() === Net_Gain_Entities::clean_tags( '' ) && array() === Net_Gain_Entities::clean_tags( null ) );

// index fixture, newest first
$index = array(
	5 => ep( 5, '2026-11-18', array( tag( 'Frontline' ), tag( 'Texas', 'place' ), tag( 'K-12 AI policy', 'topic' ) ) ),
	4 => ep( 4, '2026-11-17', array( tag( 'Frontline' ), tag( 'PowerSchool' ) ) ),
	3 => ep( 3, '2026-11-14', array( tag( 'Texas', 'place' ), tag( 'K-12 AI policy', 'topic' ) ) ),
	2 => ep( 2, '2026-11-12', array( tag( 'Frontline' ), tag( 'K-12 AI policy', 'topic' ) ) ),
	1 => ep( 1, '2026-11-10', array( tag( 'Nobody', 'organization' ) ) ),
	9 => ep( 9, '2026-11-16', array( tag( 'Frontline' ) ), 'other' ),
);
$topics = Net_Gain_Entities::build_topics( $index, 'edtech' );
check( 'topics count episodes per tag within the show', 3 === $topics['frontline']['count'] && 3 === $topics['k-12-ai-policy']['count'] && 2 === $topics['texas']['count'] );
check( 'other shows are left out', ! in_array( 9, $topics['frontline']['episodes'], true ) );
check( 'episodes are newest first and dates are first/latest', array( 5, 4, 2 ) === $topics['frontline']['episodes'] && '2026-11-12' === $topics['frontline']['first'] && '2026-11-18' === $topics['frontline']['latest'] );
check( 'each episode keeps its own note', 'n' === $topics['frontline']['notes'][5] );

$topics_all = Net_Gain_Entities::build_topics( $index );
check( 'no show filter counts every show', 4 === $topics_all['frontline']['count'] );

// place roll-up: a district newscast also counts for its province and country, with the child's note and a "via"
$pindex = array(
	3 => ep( 3, '2026-11-13', array( ptag( 'Burnaby School District', 'british-columbia', 'local', 'Portal down.' ), ptag( 'British Columbia', 'canada', 'region' ), ptag( 'Canada', '', 'country' ) ) ),
	2 => ep( 2, '2026-11-04', array( ptag( 'Central Okanagan Schools', 'british-columbia', 'local', 'Data posted.' ), ptag( 'British Columbia', 'canada', 'region', 'Hackers target the province.' ) ) ),
	1 => ep( 1, '2026-10-15', array( ptag( 'Burnaby School District', 'british-columbia', 'local', 'Breach confirmed.' ) ) ),
);
$pt = Net_Gain_Entities::build_topics( $pindex, 'edtech', strtotime( '2026-11-19' ) );
check( 'the province counts every newscast about its districts', 3 === $pt['british-columbia']['count'] );
check( 'the country rolls up through the province', array( 3, 2, 1 ) === $pt['canada']['episodes'] );
check( 'a rolled-up newscast carries the child note and via', 'Breach confirmed.' === $pt['british-columbia']['notes'][1] && 'Burnaby School District' === $pt['british-columbia']['via'][1] );
check( 'a direct tag keeps its own note and has no via', 'Hackers target the province.' === $pt['british-columbia']['notes'][2] && ! isset( $pt['british-columbia']['via'][2] ) );
check( 'parent and children are linked', 'canada' === $pt['british-columbia']['parent'] && in_array( 'burnaby-school-district', $pt['british-columbia']['children'], true ) && array( 'british-columbia' ) === $pt['canada']['children'] );
check( 'recent counts the last 30 days', 2 === $pt['british-columbia']['recent'] && 1 === $pt['burnaby-school-district']['recent'] );
check( 'clean_tags keeps parent, level and evidence', array( 'canada', 'region', 'q' ) === array_values( array_intersect_key( Net_Gain_Entities::clean_tags( array( array( 'name' => 'British Columbia', 'slug' => 'british-columbia', 'kind' => 'place', 'parent' => 'canada', 'level' => 'region', 'evidence' => 'q' ) ) )[0], array( 'parent' => 1, 'level' => 1, 'evidence' => 1 ) ) ) );
check( 'clean_tags ignores a bad parent and a self parent', '' === Net_Gain_Entities::clean_tags( array( array( 'name' => 'X', 'slug' => 'x', 'kind' => 'place', 'parent' => 'Bad Parent' ) ) )[0]['parent'] && '' === Net_Gain_Entities::clean_tags( array( array( 'name' => 'X', 'slug' => 'x', 'kind' => 'place', 'parent' => 'x' ) ) )[0]['parent'] );
check( 'every fixed topic has a blurb', 9 === count( Net_Gain_Entities::topic_blurbs() ) );

// related
$rel = Net_Gain_Entities::pick_related( $index, $topics, 5, 4 );
$ids = array_column( $rel, 'id' );
check( 'related never includes itself or another show', ! in_array( 5, $ids, true ) && ! in_array( 9, $ids, true ) );
check( 'related puts the newscasts sharing tags first', in_array( $ids[0], array( 4, 3, 2 ), true ) && $rel[0]['score'] > 0 );
check( 'related fills remaining places with unrelated newscasts, flagged by empty shared', 4 === count( $rel ) && 1 === end( $ids ) && array() === end( $rel )['shared'] );
check( 'shared names are reported', in_array( 'Frontline', $rel[0]['shared'], true ) || in_array( 'Texas', $rel[0]['shared'], true ) );
// the one sharing the rarer company+place scores above the one sharing only the broad topic
$rel3 = Net_Gain_Entities::pick_related( $index, $topics, 3, 4 );
check( 'a shared place and topic beats a shared topic alone', 5 === $rel3[0]['id'] );
// specificity: a rare shared company beats a broad topic that nearly every newscast carries
$spec = array(
	6 => ep( 6, '2026-11-18', array( tag( 'AI policy', 'topic' ), tag( 'Nelnet' ) ) ),
	5 => ep( 5, '2026-11-17', array( tag( 'AI policy', 'topic' ) ) ),
	4 => ep( 4, '2026-11-16', array( tag( 'AI policy', 'topic' ) ) ),
	3 => ep( 3, '2026-11-15', array( tag( 'AI policy', 'topic' ) ) ),
	2 => ep( 2, '2026-11-14', array( tag( 'AI policy', 'topic' ), tag( 'Nelnet' ) ) ),
	1 => ep( 1, '2026-11-13', array( tag( 'AI policy', 'topic' ) ) ),
);
$spec_topics = Net_Gain_Entities::build_topics( $spec, 'edtech' );
$spec_rel    = Net_Gain_Entities::pick_related( $spec, $spec_topics, 6, 3 );
check( 'a rare shared company outranks a broad shared topic, even against newer newscasts', 2 === $spec_rel[0]['id'] && array( 'Nelnet', 'AI policy' ) === $spec_rel[0]['shared'] );
check( 'unknown id gives nothing', array() === Net_Gain_Entities::pick_related( $index, $topics, 99, 4 ) );
check( 'limit is respected', 2 === count( Net_Gain_Entities::pick_related( $index, $topics, 5, 2 ) ) );

check( 'join_names', 'A' === Net_Gain_Entities::join_names( array( 'A' ) ) && 'A and B' === Net_Gain_Entities::join_names( array( 'A', 'B' ) ) && 'A, B and C' === Net_Gain_Entities::join_names( array( 'A', 'B', 'C' ) ) && '' === Net_Gain_Entities::join_names( array() ) );

// wording windows (search-result title 44-62 characters, description 121-160)
foreach ( array( 'PowerSchool', 'Frontline Education', 'Texas', 'Ransomware attacks on schools', 'Edtech mergers and acquisitions', 'UK Department for Education', "K\xE2\x80\x9112 AI policy", 'E-Rate program' ) as $name ) {
	$title = Net_Gain_Topic_Pages::topic_title( $name );
	$desc  = Net_Gain_Topic_Pages::topic_description( $name, 7, '2026-10-12', 'Net Gain Edtech' );
	$tl    = mb_strlen( $title );
	$dl    = mb_strlen( $desc );
	check( "title for $name is $tl characters", $tl >= 44 && $tl <= 62 );
	check( "description for $name is $dl characters", $dl >= 121 && $dl <= 160 );
}
check( 'titles use plain hyphens and never say K-12 twice', false === strpos( Net_Gain_Topic_Pages::topic_title( "K\xE2\x80\x9112 AI policy" ), "\xE2\x80\x91" ) && 1 === substr_count( Net_Gain_Topic_Pages::topic_title( "K\xE2\x80\x9112 AI policy" ), 'K-12' ) );
check( 'one newscast is singular', false !== strpos( Net_Gain_Topic_Pages::topic_description( 'Omnilert', 1, '2026-11-18', 'Net Gain Edtech' ), '1 newscast from' ) );
check( 'pick_fit takes the closest when none fit', 'abcdefgh' === Net_Gain_Topic_Pages::pick_fit( array( 'a', 'abcdefgh' ), 10, 12 ) );
$it = Net_Gain_Topic_Pages::index_title( 'Net Gain Edtech' );
$id = Net_Gain_Topic_Pages::index_description( 'Net Gain Edtech', 12, 42 );
check( 'index title/description fit', mb_strlen( $it ) >= 44 && mb_strlen( $it ) <= 62 && mb_strlen( $id ) >= 121 && mb_strlen( $id ) <= 160 );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
