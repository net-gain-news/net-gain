<?php
/**
 * Vertical: a reusable show identity/template (Spec Section 4). Not itself
 * published - title is the name, content is the starting guidelines text
 * copied into a new Show's guidelines page at creation time (Phase 2).
 *
 * show_ui=>true + show_in_menu=>false is WordPress core's own pattern for
 * "real edit screens, no nav item" - gets the native title+editor CRUD screen
 * for free (linked to from the Show screen as "+ Add New Vertical") without
 * building any custom Vertical admin UI. show_in_admin_bar isn't set
 * explicitly so it inherits show_in_menu's false, keeping it out of the
 * admin bar's "+ New" menu too.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_CPT_Vertical {

	const POST_TYPE = 'ng_vertical';

	public static function register() {
		register_post_type(
			self::POST_TYPE,
			array(
				'label'               => 'Verticals',
				'public'              => false,
				'show_ui'             => true,
				'show_in_menu'        => false,
				'show_in_rest'        => true,
				'rest_base'           => self::POST_TYPE,
				'supports'            => array( 'title', 'editor', 'revisions' ),
				'capability_type'     => array( 'ng_vertical', 'ng_verticals' ),
				'map_meta_cap'        => true,
				'hierarchical'        => false,
			)
		);
	}
}
