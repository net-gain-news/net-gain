<?php
/**
 * Plugin Name:       Net Gain Studio
 * Description:       Multi-tenant vertical newscast studio: data model and REST API for Verticals, Shows, Talent, and Episodes.
 * Version:           0.3.0
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            Net Gain
 * License:           GPL-2.0-or-later
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'NET_GAIN_VERSION', '0.3.0' );
define( 'NET_GAIN_PLUGIN_FILE', __FILE__ );
define( 'NET_GAIN_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );

require_once NET_GAIN_PLUGIN_DIR . 'includes/helpers/class-step-status.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-roles.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-talent-assignments.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-secrets.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-cpt-vertical.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-cpt-show.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-cpt-episode.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-guidelines.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/rest/class-rest-permissions.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/rest/class-rest-tick-context.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/rest/class-rest-show-actions.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/rest/class-rest-show-talent.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/rest/class-rest-episode-steps.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/rest/class-rest-secrets.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-activator.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/class-deactivator.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-shows-list-page.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-edit-show-page.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-episodes-list-page.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-episode-detail-page.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-script-review-page.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-my-show-page.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-admin-menu.php';
require_once NET_GAIN_PLUGIN_DIR . 'includes/admin/class-admin-actions.php';

register_activation_hook( __FILE__, array( 'Net_Gain_Activator', 'activate' ) );
register_deactivation_hook( __FILE__, array( 'Net_Gain_Deactivator', 'deactivate' ) );

add_action(
	'init',
	function () {
		Net_Gain_CPT_Vertical::register();
		Net_Gain_CPT_Show::register();
		Net_Gain_CPT_Episode::register();
	}
);

add_action(
	'rest_api_init',
	function () {
		( new Net_Gain_REST_Tick_Context() )->register_routes();
		( new Net_Gain_REST_Show_Actions() )->register_routes();
		( new Net_Gain_REST_Show_Talent() )->register_routes();
		( new Net_Gain_REST_Episode_Steps() )->register_routes();
		( new Net_Gain_REST_Secrets() )->register_routes();
	}
);

add_action( 'admin_menu', array( 'Net_Gain_Admin_Menu', 'register' ) );
add_action( 'admin_enqueue_scripts', array( 'Net_Gain_Admin_Menu', 'enqueue_assets' ) );
Net_Gain_Admin_Actions::register();
