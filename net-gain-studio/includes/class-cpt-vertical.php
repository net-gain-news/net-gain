<?php
/**
 * Vertical: a reusable show identity/template (Spec Section 4). Not itself
 * published - title is the name, content is the starting guidelines text
 * copied into a new Show's guidelines page at creation time (Phase 2).
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
				'show_ui'             => false,
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
