<?php
/**
 * Unit checks for includes/class-youtube-channel-guard.php.
 *
 *     php net-gain-studio/tests/youtube-channel-guard-test.php      (ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/class-youtube-channel-guard.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

$brand    = 'UCVK37sU_ajufaBqsKPpyFWw';
$personal = 'UCwQoeijp5ZJPQs0AQJNPvlQ';
$G        = 'Net_Gain_YouTube_Channel_Guard';

check( 'the pin wins over the current channel', $G::expected( $brand, $personal ) === $brand );
check( 'a show connected before the pin existed is held to its current channel', $G::expected( '', $brand ) === $brand );
check( 'a show never connected expects nothing', $G::expected( '', '' ) === '' && $G::expected( false, false ) === '' );
check( 'the first connection is always allowed', $G::allows( '', $brand ) );
check( 'the same channel may reconnect', $G::allows( $brand, $brand ) );
check( 'a different channel is refused', ! $G::allows( $brand, $personal ) );
check( 'a disconnect that cleared the current channel still holds the pin', ! $G::allows( $G::expected( $brand, '' ), $personal ) );
check( 'an unreadable channel is refused when one is expected', ! $G::allows( $brand, '' ) && ! $G::allows( $brand, null ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
