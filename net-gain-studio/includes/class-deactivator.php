<?php

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Deactivator {

	// Deliberately does not drop tables or touch any data - Section 4.2's
	// Paused/Concluded semantics apply to shows, not to plugin deactivation.
	public static function deactivate() {
		flush_rewrite_rules();
	}
}
