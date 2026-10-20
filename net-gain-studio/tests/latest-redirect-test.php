<?php
/**
 * Unit checks for the pure parts of includes/class-latest-redirect.php.
 *
 *     php net-gain-studio/tests/latest-redirect-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function add_query_arg( $k, $v, $url ) { return $url . ( false === strpos( $url, '?' ) ? '?' : '&' ) . $k . '=' . $v; }   // stand-in for WordPress's own
require __DIR__ . '/../includes/class-latest-redirect.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

check( 'show slug from the latest path', Net_Gain_Latest_Redirect::show_slug( 'edtech/latest' ) === 'edtech' );
check( 'slashes around the path are ignored', Net_Gain_Latest_Redirect::show_slug( '/edtech/latest/' ) === 'edtech' );
check( 'hyphenated show slug', Net_Gain_Latest_Redirect::show_slug( 'real-estate/latest' ) === 'real-estate' );
check( 'other paths are not a latest request', Net_Gain_Latest_Redirect::show_slug( 'edtech' ) === '' && Net_Gain_Latest_Redirect::show_slug( 'edtech/latest/more' ) === '' && Net_Gain_Latest_Redirect::show_slug( 'edtech/episodes' ) === '' && Net_Gain_Latest_Redirect::show_slug( '../latest' ) === '' && Net_Gain_Latest_Redirect::show_slug( 'latest' ) === '' );
check( 'autoplay=1 is carried through', Net_Gain_Latest_Redirect::destination( 'https://netgain.news/edtech/a/', '1' ) === 'https://netgain.news/edtech/a/?autoplay=1' );
check( 'no autoplay means a plain permalink', Net_Gain_Latest_Redirect::destination( 'https://netgain.news/edtech/a/', '' ) === 'https://netgain.news/edtech/a/' );
check( 'any other autoplay value is not carried', Net_Gain_Latest_Redirect::destination( 'https://netgain.news/edtech/a/', '0' ) === 'https://netgain.news/edtech/a/' && Net_Gain_Latest_Redirect::destination( 'https://netgain.news/edtech/a/', 'x"><script>' ) === 'https://netgain.news/edtech/a/' );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
