<?php
/**
 * Unit checks for the pure parts of includes/class-aioseo-integration.php (what AIOSEO saves for an episode page).
 *
 *     php net-gain-studio/tests/aioseo-save-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/class-aioseo-integration.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$A = 'Net_Gain_AIOSEO_Integration';
$gen_t = 'Arbor Education Breach in UK as Frontline Data Leak Hits Methuen';
$gen_d = 'Bristol\'s Southville Primary breach ties to Arbor\'s school MIS, and more.';

check( 'plain text is hand written', $A::is_hand_written( 'Data Stolen From Leading UK MIS as Frontline Leak Expands' ) );
check( 'empty is not', ! $A::is_hand_written( '' ) && ! $A::is_hand_written( "  \n" ) );
check( "AIOSEO's default template is not", ! $A::is_hand_written( '#post_title #separator_sa #site_title' ) && ! $A::is_hand_written( 'News: #post_title' ) );
check( 'a real hash in a headline is still hand written', $A::is_hand_written( '#1 edtech stock jumps as #MeToo-era rules loosen' ) );

$r = $A::resolve_save_fields( 'My title', 'My description.', $gen_t, $gen_d );
check( 'an editor\'s own title and description are kept', 'My title' === $r['title'] && 'My description.' === $r['description'] );
check( 'and reported as edits to mirror back', array( 'title' => 'My title', 'description' => 'My description.' ) === $r['edited'] );

$r = $A::resolve_save_fields( $gen_t, $gen_d, $gen_t, $gen_d );
check( 'submitting the stored text again is not an edit', array() === $r['edited'] && $gen_t === $r['title'] );

$r = $A::resolve_save_fields( '#post_title #separator_sa #site_title', '', $gen_t, $gen_d );
check( 'the untouched template and an empty description are filled from the stored text', $gen_t === $r['title'] && $gen_d === $r['description'] && array() === $r['edited'] );

$r = $A::resolve_save_fields( 'Only the title changed', $gen_d, $gen_t, $gen_d );
check( 'only the changed field is an edit', array( 'title' => 'Only the title changed' ) === $r['edited'] && $gen_d === $r['description'] );

$r = $A::resolve_save_fields( 'Padded title  ', '', '', '' );
check( 'whitespace is trimmed; nothing stored yet keeps what was submitted', 'Padded title' === $r['title'] && '' === $r['description'] );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
