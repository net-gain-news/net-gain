<?php
/**
 * Unit checks for the pure parts of includes/class-kit-profile.php.
 *
 *     php net-gain-studio/tests/kit-profile-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
require __DIR__ . '/../includes/class-kit-profile.php';

$fail = 0;
function check( $name, $cond ) { global $fail; echo ( $cond ? 'PASS ' : 'FAIL ' ) . $name . "\n"; if ( ! $cond ) { $fail++; } }

check( 'Kit key of a label', Net_Gain_Kit_Profile::field_key( 'Job title' ) === 'job_title' && Net_Gain_Kit_Profile::field_key( 'Role' ) === 'role' && Net_Gain_Kit_Profile::field_key( ' Organization ' ) === 'organization' );
check( 'every field label maps to the key the form posts', array_keys( Net_Gain_Kit_Profile::FIELDS ) === array_map( array( 'Net_Gain_Kit_Profile', 'field_key' ), array_values( Net_Gain_Kit_Profile::FIELDS ) ) );

$ok = Net_Gain_Kit_Profile::clean( array( 'email' => '  Pat@Example.COM ', 'role' => 'K-12 Administrator', 'organization' => "  Lincoln \n  District ", 'job_title' => '' ) );
check( 'address is lower-cased and trimmed, blanks dropped, spaces collapsed', $ok === array( 'email' => 'pat@example.com', 'fields' => array( 'role' => 'K-12 Administrator', 'organization' => 'Lincoln District' ) ) );

check( 'tags are stripped', Net_Gain_Kit_Profile::clean( array( 'email' => 'a@b.co', 'job_title' => '<b>Director</b><script>x()</script>' ) )['fields']['job_title'] === 'Directorx()' );
check( 'long answers are cut', mb_strlen( Net_Gain_Kit_Profile::clean( array( 'email' => 'a@b.co', 'role' => str_repeat( 'é', 500 ) ) )['fields']['role'] ) === Net_Gain_Kit_Profile::MAX_LENGTH );
check( 'unknown keys are ignored', Net_Gain_Kit_Profile::clean( array( 'email' => 'a@b.co', 'role' => 'x', 'tags' => 'evil', 'first_name' => 'y' ) )['fields'] === array( 'role' => 'x' ) );
check( 'no answers at all is not usable', null === Net_Gain_Kit_Profile::clean( array( 'email' => 'a@b.co', 'role' => '  ' ) ) );
check( 'a bad or missing address is not usable', null === Net_Gain_Kit_Profile::clean( array( 'role' => 'x' ) ) && null === Net_Gain_Kit_Profile::clean( array( 'email' => 'nope', 'role' => 'x' ) ) && null === Net_Gain_Kit_Profile::clean( array( 'email' => 'a b@c.co', 'role' => 'x' ) ) && null === Net_Gain_Kit_Profile::clean( array( 'email' => array( 'a@b.co' ), 'role' => 'x' ) ) );
check( 'non-string answers are ignored', null === Net_Gain_Kit_Profile::clean( array( 'email' => 'a@b.co', 'role' => array( 'x' ), 'organization' => 5 ) ) );

echo $fail ? "\n$fail FAILED\n" : "\nALL PASSED\n";
exit( $fail ? 1 : 0 );
