<?php
/**
 * Unit checks for the pure helpers of includes/admin/class-story-links-editor.php.
 *
 *     php net-gain-studio/tests/story-links-editor-test.php      (ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/rest/class-rest-website-publish.php';
require __DIR__ . '/../includes/admin/class-story-links-editor.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$E    = 'Net_Gain_Story_Links_Editor';
$P    = 'Net_Gain_REST_Website_Publish';
$dash = "\u{2014}";

// --- clean_rows
list( $links, $skipped ) = $E::clean_rows( array( '  Chicago   Joins <b>Protests</b> ', 'No address', '', 'Has "quotes"' ), array( 'https://a.test/1', '', '', 'https://b.test/2' ) );
check( 'tags and extra spacing are stripped from captions', 'Chicago Joins Protests' === $links[0]['title'] );
check( 'a row with a caption but no address is dropped and counted', 2 === count( $links ) && 1 === $skipped );
check( 'a fully empty row is ignored without counting', 1 === $skipped );
check( 'straight double quotes in a caption become single quotes', "Has 'quotes'" === $links[1]['title'] );
list( $bad, $n ) = $E::clean_rows( array( 'T', 'T2', 'T3' ), array( 'javascript:alert(1)', 'ftp://x.test/a', 'https://ok.test/a b' ) );
check( 'only http(s) addresses without spaces are accepted', array() === $bad && 3 === $n );
list( $auto ) = $E::clean_rows( array( '' ), array( 'https://www.example.org/path' ) );
check( 'a missing caption becomes the site name', 'example.org' === $auto[0]['title'] );
list( $many ) = $E::clean_rows( array_fill( 0, 40, 'T' ), array_fill( 0, 40, 'https://a.test/x' ) );
check( 'no more than 20 rows are kept', 20 === count( $many ) );

// --- script rewrite
$script = "Spoken text one.\n\nSpoken text two.\n\n1. \"FCC Story\" $dash https://cosn.test/fcc\n2. \"Chicago\" $dash https://techspot.test/chicago\n3. \"Microsoft\" $dash https://wf.test/ms\n";
$new    = array(
	array( 'title' => 'Chicago', 'url' => 'https://techspot.test/chicago' ),
	array( 'title' => 'Microsoft', 'url' => 'https://wf.test/ms' ),
	array( 'title' => 'FCC Story', 'url' => 'https://cosn.test/fcc' ),
);
$out = $E::rewrite_script_links( $script, $new );
check( 'the spoken text is untouched', 0 === strpos( $out, "Spoken text one.\n\nSpoken text two.\n\n" ) );
check( 'the lines come out renumbered in the new order', false !== strpos( $out, "1. \"Chicago\" $dash https://techspot.test/chicago\n2. \"Microsoft\"" ) && false !== strpos( $out, "3. \"FCC Story\" $dash https://cosn.test/fcc" ) );
$round = $P::split_script( $out );
check( 'the publish parser reads the rewritten list back in the same order', array( $new[0], $new[1], $new[2] ) === $round['links'] );
check( 'the spoken body survives the round trip', false !== strpos( $round['body'], 'Spoken text two.' ) );
check( 'rewriting twice changes nothing', $out === $E::rewrite_script_links( $out, $new ) );
$gone = $E::rewrite_script_links( $script, array() );
check( 'an empty list removes the link lines only', false === strpos( $gone, 'https://' ) && false !== strpos( $gone, 'Spoken text two.' ) );
$none = $E::rewrite_script_links( "Only spoken text.\n", $new );
check( 'a script with no link lines gets the list appended after a blank line', 0 === strpos( $none, "Only spoken text.\n" ) && false !== strpos( $none, "\n\n1. \"Chicago\"" ) );
$multi = "Body.\n\n1. \"Two sources\" $dash https://a.test/1 and https://b.test/2\n2. \"One\" $dash https://c.test/3\n";
$mout  = $E::rewrite_script_links( $multi, array( array( 'title' => 'One', 'url' => 'https://c.test/3' ) ) );
check( 'a line that carried two addresses is replaced like any other', 1 === substr_count( $mout, 'https://' ) );
$head = "Body.\n\n**Stories & links:**\n1. \"A\" $dash https://a.test/1\n";
check( 'a heading above the links is kept', false !== strpos( $E::rewrite_script_links( $head, $new ), '**Stories & links:**' ) );

// --- notes rewrite
$notes = '<p>Intro.</p><p><strong>Stories &amp; links:</strong></p><p>"FCC Story" ' . $dash . ' <a href="https://cosn.test/fcc" rel="nofollow">https://cosn.test/fcc</a></p>';
$nout  = $E::rewrite_notes_links( $notes, $new );
check( 'the intro of the notes is untouched', 0 === strpos( $nout, '<p>Intro.</p><p><strong>Stories &amp; links:</strong></p>' ) );
check( 'the notes list the stories in the new order', strpos( $nout, 'Chicago' ) < strpos( $nout, 'Microsoft' ) && strpos( $nout, 'Microsoft' ) < strpos( $nout, 'FCC Story' ) );
check( 'notes without the heading are returned unchanged', '<p>Plain.</p>' === $E::rewrite_notes_links( '<p>Plain.</p>', $new ) );
$amp = $E::rewrite_notes_links( $notes, array( array( 'title' => 'A & B <i>', 'url' => 'https://a.test/?x=1&y=2' ) ) );
check( 'ampersands and angle brackets are escaped in the notes', false !== strpos( $amp, 'A &amp; B &lt;i&gt;' ) && false !== strpos( $amp, 'x=1&amp;y=2' ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
