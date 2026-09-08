<?php
/**
 * Episode: the pipeline's own internal record (Spec Section 4) - draft/final
 * script, step statuses, generated metadata, file references. Deliberately
 * NOT the public podcast page: that's a separate Seriously Simple Podcasting
 * post created later at "website published" time (Phase 6), referenced here
 * via ng_website_post_id once it exists. Keeping them separate means a draft
 * script or in-progress step status can never be reachable by a site visitor.
 *
 * hierarchical=true is set purely so WP_REST_Posts_Controller exposes native
 * ?parent={show_id} filtering - no custom "list this show's episodes" route
 * needed. post_date is set to the episode's real date so the dashboard
 * (Phase 7) can use native after/before/orderby=date REST params too.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_CPT_Episode {

	const POST_TYPE = 'ng_episode';

	public static function register() {
		register_post_type(
			self::POST_TYPE,
			array(
				'label'           => 'Episodes',
				'public'          => false,
				'show_ui'         => false,
				'show_in_menu'    => false,
				'show_in_rest'    => true,
				'rest_base'       => self::POST_TYPE,
				'supports'        => array( 'title', 'author' ),
				'capability_type' => array( 'ng_episode', 'ng_episodes' ),
				'map_meta_cap'    => true,
				'hierarchical'    => true,
			)
		);

		self::register_meta();
	}

	private static function register_meta() {
		$auth_callback = function ( $allowed, $meta_key, $post_id ) {
			return current_user_can( 'edit_post', $post_id );
		};

		$fields = array(
			'ng_episode_date'          => array( 'type' => 'string', 'default' => '' ),
			'ng_script_draft'          => array( 'type' => 'string', 'default' => '' ),
			'ng_script_final'          => array( 'type' => 'string', 'default' => '' ),
			'ng_audio_attachment_id'   => array( 'type' => 'integer', 'default' => 0 ),
			'ng_image_square_id'       => array( 'type' => 'integer', 'default' => 0 ),
			'ng_image_16x9_id'         => array( 'type' => 'integer', 'default' => 0 ),
			'ng_image_1200x630_id'     => array( 'type' => 'integer', 'default' => 0 ),
			'ng_meta_captivate_title'  => array( 'type' => 'string', 'default' => '' ),
			'ng_meta_captivate_notes'  => array( 'type' => 'string', 'default' => '' ),
			'ng_meta_aioseo_title'       => array( 'type' => 'string', 'default' => '' ),
			'ng_meta_aioseo_description' => array( 'type' => 'string', 'default' => '' ),
			'ng_meta_youtube_title'       => array( 'type' => 'string', 'default' => '' ),
			'ng_meta_youtube_description' => array( 'type' => 'string', 'default' => '' ),
			'ng_meta_youtube_tags'        => array(
				'type'    => 'array',
				'default' => array(),
				'show_in_rest' => array( 'schema' => array( 'type' => 'array', 'items' => array( 'type' => 'string' ) ) ),
			),
			// Written only after re-fetching and confirming the live result (Spec Section 9) -
			// never populated from a create-call's success response alone.
			'ng_url_captivate' => array( 'type' => 'string', 'default' => '' ),
			'ng_url_website'   => array( 'type' => 'string', 'default' => '' ),
			'ng_url_youtube'   => array( 'type' => 'string', 'default' => '' ),
			'ng_website_post_id' => array( 'type' => 'integer', 'default' => 0 ),
			// Snapshotted at finalization - never re-derived from the Show's *current*
			// primary talent, per Spec Section 4.1's prospective-only-changes rule.
			'ng_talent_user_id' => array( 'type' => 'integer', 'default' => 0 ),
			'ng_step_status'    => array(
				'type'         => 'object',
				'default'      => Net_Gain_Step_Status::default_status(),
				'show_in_rest' => array( 'schema' => Net_Gain_Step_Status::rest_schema() ),
			),
			'ng_finalization' => array(
				'type'    => 'object',
				'default' => array(
					'state'               => 'pending', // pending|counting_down|awaiting_replacement|finalized|aborted
					'countdown_started_at' => null,
					'countdown_seconds'    => 90,
				),
				'show_in_rest' => array(
					'schema' => array(
						'type'       => 'object',
						'properties' => array(
							'state'                => array( 'type' => 'string' ),
							'countdown_started_at' => array( 'type' => array( 'string', 'null' ) ),
							'countdown_seconds'    => array( 'type' => 'integer' ),
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
