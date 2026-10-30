<?php
/**
 * Keeps the address a visitor just signed up with for the welcome page.
 *
 * Kit's own sign-up script sends the subscriber on to the welcome page and fires a page event with the address just before
 * it does; assets/signup-handoff.js keeps it for that browser tab, so the welcome page's Kit form can send the optional
 * answers for the right subscriber.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Signup_Handoff {

	public static function register() {
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue' ) );
	}

	public static function enqueue() {
		$file = NET_GAIN_PLUGIN_DIR . 'assets/signup-handoff.js';
		wp_enqueue_script( 'ng-signup-handoff', plugin_dir_url( NET_GAIN_PLUGIN_FILE ) . 'assets/signup-handoff.js', array(), NET_GAIN_VERSION . '.' . (int) @filemtime( $file ), true );
	}
}
