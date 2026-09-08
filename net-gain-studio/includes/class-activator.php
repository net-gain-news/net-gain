<?php

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Activator {

	public static function activate() {
		Net_Gain_Talent_Assignments::create_table();
		Net_Gain_Secrets::create_table();
		Net_Gain_Roles::register_roles();
		Net_Gain_Roles::grant_capabilities();

		// CPTs must be registered before flushing so their rewrite rules are included.
		Net_Gain_CPT_Vertical::register();
		Net_Gain_CPT_Show::register();
		Net_Gain_CPT_Episode::register();
		flush_rewrite_rules();

		update_option( 'ng_db_version', NET_GAIN_VERSION );
	}
}
