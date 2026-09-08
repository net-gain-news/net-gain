<?php
/**
 * Show: one underwriter's live deployment of a Vertical (Spec Section 4).
 * post_name (the CPT's own slug) doubles as the website subdirectory slug -
 * no separate meta key, gets WP's native uniqueness/sanitization for free.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_CPT_Show {

	const POST_TYPE = 'ng_show';

	public static function register() {
		register_post_type(
			self::POST_TYPE,
			array(
				'label'           => 'Shows',
				'public'          => false,
				'show_ui'         => false,
				'show_in_menu'    => false,
				'show_in_rest'    => true,
				'rest_base'       => self::POST_TYPE,
				'supports'        => array( 'title' ),
				'capability_type' => array( 'ng_show', 'ng_shows' ),
				'map_meta_cap'    => true,
				'hierarchical'    => false,
			)
		);

		self::register_meta();
	}

	private static function register_meta() {
		$auth_callback = function ( $allowed, $meta_key, $post_id ) {
			return current_user_can( 'edit_post', $post_id );
		};

		$fields = array(
			'ng_vertical_id'         => array( 'type' => 'integer', 'default' => 0 ),
			'ng_custom_domain'       => array( 'type' => 'string', 'default' => '' ),
			'ng_recording_days'      => array(
				'type'       => 'array',
				'default'    => array(),
				'show_in_rest' => array(
					'schema' => array(
						'type'  => 'array',
						'items' => array( 'type' => 'string', 'enum' => array( 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun' ) ),
					),
				),
			),
			'ng_target_time'         => array( 'type' => 'string', 'default' => '' ),
			'ng_recording_timezone'  => array( 'type' => 'string', 'default' => '' ),
			'ng_lookback_days'       => array( 'type' => 'integer', 'default' => 30 ),
			'ng_guidelines_page_id'  => array( 'type' => 'integer', 'default' => 0 ),
			'ng_frame_square_id'     => array( 'type' => 'integer', 'default' => 0 ),
			'ng_frame_16x9_id'       => array( 'type' => 'integer', 'default' => 0 ),
			'ng_frame_1200x630_id'   => array( 'type' => 'integer', 'default' => 0 ),
			'ng_status'              => array( 'type' => 'string', 'default' => 'active' ), // active|paused|concluded - never "archived", see Spec 4.2.
			'ng_captivate_show_id'   => array( 'type' => 'string', 'default' => '' ),
			'ng_youtube_channel_id'  => array( 'type' => 'string', 'default' => '' ), // non-secret; OAuth tokens live in wp_ng_secrets.
			'ng_publish_mode'        => array( 'type' => 'string', 'default' => 'immediate' ), // immediate|scheduled
			'ng_publish_time'        => array( 'type' => 'string', 'default' => '' ),
			'ng_publish_timezone'    => array( 'type' => 'string', 'default' => '' ),
			'ng_pending_actions'     => array(
				'type'    => 'array',
				'default' => array(),
				'show_in_rest' => array(
					'schema' => array(
						'type'  => 'array',
						'items' => array(
							'type'       => 'object',
							'properties' => array(
								'id'           => array( 'type' => 'string' ),
								'action'       => array( 'type' => 'string' ),
								'episode_date' => array( 'type' => 'string' ),
								'requested_at' => array( 'type' => 'string' ),
								'requested_by' => array( 'type' => 'integer' ),
								'status'       => array( 'type' => 'string' ),
							),
						),
					),
				),
			),
		);

		foreach ( $fields as $key => $args ) {
			register_post_meta(
				self::POST_TYPE,
				$key,
				array_merge(
					array(
						'single'        => true,
						'show_in_rest'  => true,
						'auth_callback' => $auth_callback,
					),
					$args
				)
			);
		}
	}
}
