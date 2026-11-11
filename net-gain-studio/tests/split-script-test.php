<?php
/**
 * Unit checks for the links-section parser in includes/rest/class-rest-website-publish.php.
 *
 *     php net-gain-studio/tests/split-script-test.php      (ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/rest/class-rest-website-publish.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$P = 'Net_Gain_REST_Website_Publish';
$dash = "\u{2014}";

// --- one line
$one = $P::parse_link_line( "1. \u{201C}South Portland Rejects AI Moratorium\u{201D} $dash https://fox23maine.com/a-b" );
check( 'single address parses', $one && 'South Portland Rejects AI Moratorium' === $one['title'] && array( 'https://fox23maine.com/a-b' ) === $one['urls'] );
$two = $P::parse_link_line( "1. \"Title, With Comma\" $dash https://www.wric.com/a/ and https://www.example.com/id/Umlj" );
check( 'two addresses joined by "and" both parse', $two && 'Title, With Comma' === $two['title'] && 2 === count( $two['urls'] ) && 'https://www.example.com/id/Umlj' === $two['urls'][1] );
$three = $P::parse_link_line( "2. Title $dash https://a.com/x, https://b.com/y; https://c.com/z" );
check( 'commas and semicolons join addresses', $three && 3 === count( $three['urls'] ) && 'https://a.com/x' === $three['urls'][0] );
$amp = $P::parse_link_line( "3. Title $dash https://a.com/x & https://b.com/y" );
check( 'ampersand joins addresses', $amp && 2 === count( $amp['urls'] ) );
check( 'prose after the address is not a link line', null === $P::parse_link_line( "1. Title $dash https://a.com/x is a great read" ) );
check( 'a hyphen is not the separator', null === $P::parse_link_line( '1. K-12 News - https://a.com/x' ) );
check( 'a spoken numbered line without an address is not a link line', null === $P::parse_link_line( '1. Make sure to follow the show.' ) );
check( 'trailing comma is not part of the address', array( 'https://a.com/x' ) === $P::parse_link_line( "1. T $dash https://a.com/x," )['urls'] );

// --- whole script: the 2026-11-10 shape (link 1 has two addresses)
$script = "Welcome.\n\nThat's the show.\n\n**Show notes $dash story names and links:**\n"
	. "1. \"Ransomware Group Claims Richmond\" $dash https://www.wric.com/a/ and https://www.ransomware.live/id/x\n"
	. "2. \"South Portland\" $dash https://fox23maine.com/b\n"
	. "3. \"Nerdy Slides\" $dash https://www.gurufocus.com/c\n";
$r = $P::split_script( $script );
check( 'link 1 with two addresses starts the list', 4 === count( $r['links'] ) && 'https://www.wric.com/a/' === $r['links'][0]['url'] && 'Ransomware Group Claims Richmond' === $r['links'][0]['title'] );
check( 'the second address of line 1 follows it, same caption', 'https://www.ransomware.live/id/x' === $r['links'][1]['url'] && $r['links'][0]['title'] === $r['links'][1]['title'] );
check( 'links 2 and 3 follow in order', 'https://fox23maine.com/b' === $r['links'][2]['url'] && 'https://www.gurufocus.com/c' === $r['links'][3]['url'] );
check( 'the header and link 1 no longer stay in the body', false === strpos( $r['body'], 'Show notes' ) && false === strpos( $r['body'], 'Richmond' ) && "That's the show." === substr( $r['body'], -16 ) );

// --- ordinary scripts behave exactly as before
$plain = "Intro.\n\nSign-off.\n\n1. \"A\" $dash https://a.com/1\n2. \"B\" $dash https://b.com/2\n";
$r = $P::split_script( $plain );
check( 'plain two-link script: two links, body ends at the sign-off', 2 === count( $r['links'] ) && 'Sign-off.' === substr( $r['body'], -9 ) );
$none = $P::split_script( "Just a script.\n\nNo links here." );
check( 'no links section: body unchanged, no links', array() === $none['links'] && "Just a script.\n\nNo links here." === $none['body'] );
$spoken = "A list: 1. First thing. 2. Second thing.\n\nBye.\n\n1. \"A\" $dash https://a.com/1\n";
$r = $P::split_script( $spoken );
check( 'numbered spoken text before the section is left in the body', 1 === count( $r['links'] ) && false !== strpos( $r['body'], 'A list: 1. First thing.' ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
